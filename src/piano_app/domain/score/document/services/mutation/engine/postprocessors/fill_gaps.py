from collections.abc import Sequence
from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.geometry import Point, Span, gaps
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    PlaceSpansRequest,
    RestContent,
)
from piano_app.domain.score.document.services.resolution import resolve_staff

from .base import MutatedStatePostprocessor
from .content import holds_content


@dataclass(frozen=True, slots=True, kw_only=True)
class _Segment:
    """The part of one scope inside one measure, written in the scope's own frame, and the
    rooms of the scope's children reaching into that measure."""

    measure: Measure
    bucket: Span
    covered: Sequence[Span]


class FillGapsPostprocessor(MutatedStatePostprocessor):
    """Keeps every occupied region of every voice tiled, filling what is left with rests.

    Geometry reports holes without judging them; which holes deserve rests is decided
    here, and the two rules are deliberately NOT symmetric:

    * a measure the voice holds nothing in is **asleep** and is skipped, so an empty
      voice stays empty instead of sprouting rests;
    * a tuplet that exists has its interior occupied by definition, so it is **always**
      tiled in full and never sleeps, childless or not — whether it stays was judged
      before the fill, and it wakes every measure it reaches.

    Only holes are filled; an existing rest is never touched, merged or respelled. Each
    hole of a scope inside one measure is placed as one rest item over the whole hole —
    cut and spelled into the largest values by the spans, its pieces untied — on the
    staff resolved for the hole. So a second pass finds no hole.

    Every scope is read measure by measure, through what of it reaches into each measure.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[PlaceSpansRequest]:
        regions: list[tuple[Measure, Span]] = geometry.measure_regions()

        fixes: list[PlaceSpansRequest] = []
        for voice in document.voices:
            for measure, region in regions:
                contents: list[tuple[RhythmicContainer, Span]] = geometry.contents_in(
                    scope=voice,
                    measure=measure,
                )

                # THE SLEEPING RULE. A measure the voice holds nothing in is asleep, not
                # empty: it is not a bucket at all, so nothing fills it. What holds
                # something is a note or a rest — or a group, which this very pass tiles
                # with rests, so the fill leaves what a second pass would leave. Drop this
                # filter and every silent measure of every voice sprouts rests.
                if not any(
                    isinstance(child, GroupRhythmicContainer) or holds_content(container=child)
                    for child, _ in contents
                ):
                    continue

                segment: _Segment = _Segment(
                    measure=measure,
                    bucket=region,
                    covered=[span for _, span in contents],
                )
                fixes.extend(self._tile(geometry=geometry, voice=voice, segment=segment))

            fixes.extend(self._tile_groups(geometry=geometry, voice=voice, scope=voice))

        return fixes

    def _tile_groups(
        self,
        *,
        geometry: ScoreGeometry,
        voice: Voice,
        scope: Voice | GroupRhythmicContainer,
    ) -> list[PlaceSpansRequest]:
        fixes: list[PlaceSpansRequest] = []

        for child in scope.children:
            if not isinstance(child, GroupRhythmicContainer):
                continue

            # no sleeping rule here, on purpose: the group's whole interior is live while
            # the group exists; it is cut at the barlines it crosses, in its own frame,
            # from the measure it starts in to the last one it reaches
            reach: Span = geometry.global_span_of(container=child)
            measure: Measure | None = child.start_anchor.measure
            while measure is not None:
                part: Span | None = geometry.measure_span(measure=measure).intersection(reach)
                if part is None:
                    break

                segment: _Segment = _Segment(
                    measure=measure,
                    bucket=part.to(frame=geometry.of_group(group=child)),
                    covered=[
                        span for _, span in geometry.contents_in(scope=child, measure=measure)
                    ],
                )
                fixes.extend(self._tile(geometry=geometry, voice=voice, segment=segment))
                measure = measure.next_measure

            fixes.extend(self._tile_groups(geometry=geometry, voice=voice, scope=child))

        return fixes

    def _tile(
        self,
        *,
        geometry: ScoreGeometry,
        voice: Voice,
        segment: _Segment,
    ) -> list[PlaceSpansRequest]:
        """Places one rest item over every hole of the segment."""
        fixes: list[PlaceSpansRequest] = []
        for hole in gaps(bucket=segment.bucket, covered=segment.covered):
            # one hole, one staff: chosen once for every rest the item is spelled into
            try:
                staff: Staff = resolve_staff(geometry=geometry, voice=voice, gap=hole)
            except ValueError as error:
                raise MutationRejectedError(str(error)) from error

            # the item is addressed from its voice: a hole holds no group's start, so the
            # deepest scope at its start is the scope it lies in, and its length is written
            # in that scope's units
            start: Point = hole.start_point.to(frame=geometry.root)
            fixes.append(
                PlaceSpansRequest(
                    voice=voice,
                    measure=segment.measure,
                    position=MeasurePosition.of_fraction(
                        fraction=start.to(frame=geometry.of_measure(measure=segment.measure)).value
                    ),
                    written_length=hole.length,
                    content=RestContent(staff=staff),
                )
            )

        return fixes
