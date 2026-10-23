from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.indexing import Index

from .errors import OutsideFrameError
from .frame import Frame
from .transform import Transform

# The spaces of the score: the timeline, the measures on it and the squeezed interior of
# every tuplet group, as frames. This module and ``occupancy`` are the only places in
# `geometry` that know the score model exists. Everything else works on frames alone,
# which is what keeps the mechanism testable without a document and reusable for spaces we
# have not invented yet.


@dataclass(frozen=True, slots=True, kw_only=True)
class _Chain:
    """The measures in order and where each begins on the timeline.

    The only absolute coordinates the index keeps: a container's place is always read from
    its anchor, so a measure edit rebuilds this and nothing it merely shifts.
    """

    measures: list[Measure]
    # one entry more than ``measures``: the last is where the timeline ends
    starts: list[Fraction]
    indexes: dict[Measure, int]


class SpacesIndex(Index):
    """The numbers of the live model that place things on the timeline, built lazily and
    kept until told what changed.

    Two kinds of fragment, each healed on its own when read dirty: the measure chain, and
    each group's scale on the timeline. A dirty fragment is simply absent.
    """

    def __init__(self, *, document: ScoreDocument) -> None:
        self._document: ScoreDocument = document
        self._chain: _Chain | None = None
        self._scales: dict[GroupRhythmicContainer, Fraction] = {}

    @property
    def extent(self) -> Fraction:
        return self._read_chain().starts[-1]

    @property
    def measures(self) -> Sequence[Measure]:
        return self._read_chain().measures

    def measure_start(self, *, measure: Measure) -> Fraction:
        """Where the measure begins on the timeline. Measures shift, they never compress."""
        chain: _Chain = self._read_chain()

        return chain.starts[chain.indexes[measure]]

    def measure_at(self, *, value: Fraction) -> Measure | None:
        """The measure holding a timeline value, found by binary search; ``None`` outside
        the timeline."""
        chain: _Chain = self._read_chain()
        if not 0 <= value < chain.starts[-1]:
            return None

        return chain.measures[bisect_right(chain.starts, value) - 1]

    def measures_between(self, *, start: Fraction, end: Fraction) -> Sequence[Measure]:
        """The measures the half-open timeline range ``[start, end)`` reaches into, in order.

        A range lying past the timeline reaches none.
        """
        chain: _Chain = self._read_chain()
        first: int = max(bisect_right(chain.starts, start) - 1, 0)

        return chain.measures[first : bisect_left(chain.starts, end)]

    def measures_from(self, *, measure: Measure, end: Fraction) -> Sequence[Measure]:
        """The measures from ``measure`` on that begin before the timeline value ``end``, in
        order: the ones a room starting in ``measure`` and ending at ``end`` reaches into.
        Half-open: a room ending on a barline does not reach past it."""
        chain: _Chain = self._read_chain()
        first: int = chain.indexes[measure]
        last: int = first
        while last < len(chain.measures) and chain.starts[last] < end:
            last += 1

        return chain.measures[first:last]

    def anchor_position(self, *, anchor: TemporalAnchor) -> Fraction:
        return self.measure_start(measure=anchor.measure) + anchor.position.value

    def scale_of(self, *, scope: RhythmicContainerParent) -> Fraction:
        """How long one unit of the scope lasts on the timeline — every enclosing group's
        compression, multiplied. A voice sits on the timeline, so it is one."""
        if not isinstance(scope, GroupRhythmicContainer):
            return Fraction(1)

        scale: Fraction | None = self._scales.get(scope)
        if scale is None:
            scale = (
                scope.occupied_size.fraction
                / scope.written_size.fraction
                * self.scale_of(scope=scope.parent)
            )
            self._scales[scope] = scale

        return scale

    def invalidate_measures(self) -> None:
        # a measure shifts every later one
        self._chain = None

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        # a group's scale reaches everything under it: how long each nested container lasts
        # on the timeline
        pending: list[GroupRhythmicContainer] = [group]
        while pending:
            nested: GroupRhythmicContainer = pending.pop()
            self._scales.pop(nested, None)
            pending.extend(
                child for child in nested.children if isinstance(child, GroupRhythmicContainer)
            )

    def _read_chain(self) -> _Chain:
        if self._chain is None:
            measures: list[Measure] = list(self._document.measures)
            starts: list[Fraction] = [Fraction(0)]
            indexes: dict[Measure, int] = {}

            for index, measure in enumerate(measures):
                indexes[measure] = index
                starts.append(starts[-1] + measure.time_signature.fraction)

            self._chain = _Chain(measures=measures, starts=starts, indexes=indexes)

        return self._chain


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoreFrame:
    """The score's whole timeline as a coordinate space — the root every other frame
    maps into, and the space a voice's containers sit in.

    ``document`` identifies the timeline: two roots over one document are equal, so frames
    built by separate geometries combine, while two documents are what
    ``UnreachableFrameError`` catches. The numbers, the length among them, are the
    index's — the timeline ends where the last measure does.
    """

    document: ScoreDocument
    # not part of what the frame stands for: equal frames may be read through different
    # indexes
    index: SpacesIndex = field(compare=False)

    @property
    def parent(self) -> None:
        return None

    @property
    def to_parent(self) -> Transform:
        return Transform.identity()

    @property
    def extent(self) -> Fraction:
        return self.index.extent


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureFrame:
    """A measure as a coordinate space: the degenerate frame that shifts without
    compressing."""

    source: Measure
    root: ScoreFrame

    @property
    def parent(self) -> ScoreFrame:
        return self.root

    @property
    def to_parent(self) -> Transform:
        return Transform.of_shift(offset=self.root.index.measure_start(measure=self.source))

    @property
    def extent(self) -> Fraction:
        return self.source.time_signature.fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupFrame:
    """A tuplet group as a coordinate space — its written interior, squeezed into the
    room it occupies outside."""

    source: GroupRhythmicContainer
    root: ScoreFrame

    @property
    def parent(self) -> Frame:
        return frame_of_scope(scope=self.source.parent, root=self.root)

    @property
    def to_parent(self) -> Transform:
        return Transform.of_nesting(
            written=self.source.written_size.fraction,
            occupied=self.source.occupied_size.fraction,
            offset=offset_in_parent(container=self.source, root=self.root),
        )

    @property
    def extent(self) -> Fraction:
        return self.source.written_size.fraction


def frame_of_scope(*, scope: RhythmicContainerParent, root: ScoreFrame) -> Frame:
    """The coordinate space a parent stands for.

    Translating a model shape into a frame is exactly this module's job, and everything
    above it works on frames alone.
    """
    if isinstance(scope, GroupRhythmicContainer):
        return GroupFrame(source=scope, root=root)

    # a voice owns a set of children but is not a coordinate space of its own — it
    # starts nowhere and compresses nothing, so its containers sit directly on the
    # score's timeline
    if isinstance(scope, Voice):
        return root

    raise TypeError(f"Scope is not a voice or a group: {scope!r}")


def offset_in_parent(*, container: RhythmicContainer, root: ScoreFrame) -> Fraction:
    """Where the container begins inside its parent frame: its own anchor, restated there.

    One rule for a voice and a group. Never packed from the earlier siblings — in the
    middle of a gesture a sibling may be missing, while the container's anchor is its
    position regardless. Raises ``OutsideFrameError`` when the anchor does not fall
    inside the group: a start on its far end still does, like any point on a boundary.
    Read from the index's numbers rather than by converting frames, which would walk every
    enclosing group's own offset again.
    """
    parent: RhythmicContainerParent = container.parent
    start: Fraction = root.index.anchor_position(anchor=container.start_anchor)

    # a voice is not a frame: its containers sit directly on the timeline
    if not isinstance(parent, GroupRhythmicContainer):
        return start

    # a group starts at its own anchor, so its interior's zero lies there
    origin: Fraction = root.index.anchor_position(anchor=parent.start_anchor)
    offset: Fraction = (start - origin) / root.index.scale_of(scope=parent)
    if not 0 <= offset <= parent.written_size.fraction:
        raise OutsideFrameError(
            f"Coordinate {offset} lies outside the group's extent {parent.written_size.fraction}."
        )

    return offset
