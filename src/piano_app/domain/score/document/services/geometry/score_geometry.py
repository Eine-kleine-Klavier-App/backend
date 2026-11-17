from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import SpanContext
from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.indexing import Index

from .coordinates import Point, Span
from .frame import Frame, conversion
from .occupancy import OccupancyIndex
from .queries import Meeting, containing, footprint, meetings
from .spaces import (
    GroupFrame,
    MeasureFrame,
    ScoreFrame,
    SpacesIndex,
    frame_of_scope,
    offset_in_parent,
)
from .transform import Transform


class ScoreGeometry(Index):
    """Reads the live score as frames, through an index of it.

    It is made of two indexes, the spaces and what occupies them, each built lazily, fragment
    by fragment, and kept: after the model changes, call the ``invalidate_*`` method of what
    changed, and the next read heals only what that dirtied. A read without it may answer for
    the score as it was. The geometry may be held across an edit; the spans and points it
    returns are snapshots and may not.
    """

    def __init__(self, *, document: ScoreDocument) -> None:
        self._spaces: SpacesIndex = SpacesIndex(document=document)
        self._occupancy: OccupancyIndex = OccupancyIndex(spaces=self._spaces)
        self._root: ScoreFrame = ScoreFrame(document=document, index=self._spaces)

    @property
    def root(self) -> Frame:
        """The global timeline both measures and rhythm project into."""
        return self._root

    def of_measure(self, *, measure: Measure) -> Frame:
        return MeasureFrame(source=measure, root=self._root)

    def of_group(self, *, group: GroupRhythmicContainer) -> Frame:
        return GroupFrame(source=group, root=self._root)

    def of_scope(self, *, scope: RhythmicContainerParent) -> Frame:
        """The space a voice or a group stands for."""
        return frame_of_scope(scope=scope, root=self._root)

    def measure_span(self, *, measure: Measure) -> Span:
        """The measure's room on the global timeline."""
        return footprint(frame=self.of_measure(measure=measure))

    def span_of(self, *, container: RhythmicContainer) -> Span:
        """The room the container takes in its parent frame.

        A group answers this with its ``occupied_size`` while its own interior
        measures ``written_size`` — the two halves of being both a frame and placed.
        """
        return Span(
            frame=frame_of_scope(scope=container.parent, root=self._root),
            start=offset_in_parent(container=container, root=self._root),
            length=container.occupied_size.fraction,
        )

    def global_span_of(self, *, container: RhythmicContainer) -> Span:
        """The container's room on the global timeline."""
        return self.span_of(container=container).to(frame=self._root)

    def point_of(self, *, anchor: TemporalAnchor) -> Point:
        """An anchor's location on the global timeline."""
        return Point(frame=self._root, value=self._spaces.anchor_position(anchor=anchor))

    def end_of(self, *, context: SpanContext) -> Point:
        """Where a span context ends on the global timeline; a span without an end lasts until
        the end of the score."""
        if context.end is None:
            return Point(frame=self._root, value=self._root.extent)

        return self.point_of(anchor=context.end)

    def contents_of(
        self,
        *,
        scope: RhythmicContainerParent,
    ) -> list[tuple[RhythmicContainer, Span]]:
        """What sits in a scope, ready to be handed to ``meetings`` / ``containing``."""
        return [(child, self.span_of(container=child)) for child in scope.children]

    def contents_in(
        self,
        *,
        scope: RhythmicContainerParent,
        measure: Measure,
    ) -> list[tuple[RhythmicContainer, Span]]:
        """What of a scope reaches into one measure, in the form of ``contents_of``.

        A child crossing a barline is listed in every measure it reaches; one ending
        exactly on a barline is not listed in the measure after it.
        """
        return [
            (child, self.span_of(container=child))
            for child in self._occupancy.find_children_in(scope=scope, measure=measure)
        ]

    def measure_regions(self) -> list[tuple[Measure, Span]]:
        """The measures as regions of the global timeline, in order."""
        return [(measure, self.measure_span(measure=measure)) for measure in self._spaces.measures]

    def measure_at(self, *, point: Point) -> Measure | None:
        """Which measure holds the point, or ``None`` past the end of the score.

        ``None`` rather than an error: running off the end is something the caller
        answers for (reject the edit, append a measure), not a geometric impossibility.
        """
        return self._spaces.measure_at(value=point.to(frame=self._root).value)

    def slice_by_measures(self, *, span: Span) -> list[Meeting[Measure]]:
        """Cut a span at the barlines it crosses.

        Returns every piece; a single piece means it stayed inside one measure. What
        to do with more than one — tie them together, refuse the edit — is the
        caller's call, which is why this reports instead of rejecting.
        """
        regions: list[tuple[Measure, Span]] = [
            (measure, self.measure_span(measure=measure))
            for measure in self._measures_reached_by(span=span)
        ]

        return meetings(span=span.to(frame=self._root), candidates=regions)

    def intersecting(
        self,
        *,
        span: Span,
        scope: RhythmicContainerParent,
    ) -> list[Meeting[RhythmicContainer]]:
        """What already sits where the span wants to go."""
        # a child crossing a barline is listed in each measure it reaches
        reached: dict[RhythmicContainer, None] = dict.fromkeys(
            child
            for measure in self._measures_reached_by(span=span)
            for child in self._occupancy.find_children_in(scope=scope, measure=measure)
        )

        return meetings(
            span=span,
            candidates=[(child, self.span_of(container=child)) for child in reached],
        )

    def deepest_scope_at(
        self,
        *,
        point: Point,
        voice: Voice,
    ) -> tuple[RhythmicContainerParent, Point]:
        """Descend to the innermost space holding the point, restating it on the way.

        Returns the scope AND the point in that scope's coordinates, so the caller can
        build a span there directly. Nothing is rejected: a requested size that will
        not fit the scope it lands in is reported by ``overflow`` afterwards, and what
        that means is the caller's to decide.
        """
        scope: RhythmicContainerParent = voice
        local: Point = point.to(frame=self._root)
        measure: Measure | None = self._spaces.measure_at(value=local.value)

        # a point on the timeline's far end lies in no measure, so in no group
        while measure is not None:
            nested: list[tuple[GroupRhythmicContainer, Span]] = [
                (child, self.span_of(container=child))
                for child in self._occupancy.find_children_in(scope=scope, measure=measure)
                if isinstance(child, GroupRhythmicContainer)
            ]

            entered: GroupRhythmicContainer | None = containing(point=local, candidates=nested)
            if entered is None:
                break

            scope = entered
            local = local.to(frame=self.of_group(group=entered))

        return scope, local

    def invalidate_measures(self) -> None:
        """A measure was created or deleted, or its time signature changed.

        Every layout goes and heals per scope; measure-level edits are rare.
        """
        self._spaces.invalidate_measures()
        self._occupancy.invalidate_measures()

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        """An anchor was created, deleted or moved — delivered after the change, so a move
        to another measure reads the containers where they landed."""
        self._occupancy.invalidate_anchor(anchor=anchor)

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        """A leaf was created, deleted or resized — delivered after the change: a detached
        leaf keeps its parent."""
        self._occupancy.invalidate_leaf(leaf=leaf)

    def invalidate_child(self, *, scope: RhythmicContainerParent, child: RhythmicContainer) -> None:
        """A child was attached to or detached from the scope — delivered after the change.
        Only that child is read again; what lies under it is untouched."""
        self._occupancy.invalidate_child(scope=scope, child=child)

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        """A group was created, deleted, resized or split — delivered after the change:
        a detached group keeps its parent. Everything under it goes too, since its scale
        reaches all of it."""
        self._spaces.invalidate_group(group=group)
        self._occupancy.invalidate_group(group=group)

    def _measures_reached_by(self, *, span: Span) -> Sequence[Measure]:
        """The measures a span reaches into. Restated without a containment check, so a
        span overflowing its frame still reaches what lies inside the timeline."""
        transform: Transform = conversion(source=span.frame, target=self._root)
        start: Fraction = transform.apply_position(span.start)

        return self._spaces.measures_between(
            start=start,
            end=start + transform.apply_length(span.length),
        )
