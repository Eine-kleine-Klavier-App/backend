from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Rest
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
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
from piano_app.domain.score.document.services.geometry import Point, Span, gaps, interior
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import RhythmicSizeMapper
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateRestRequest,
)
from piano_app.domain.score.document.services.resolution import resolve_staff

from .base import MutatedStatePostprocessor


class FillGapsPostprocessor(MutatedStatePostprocessor):
    """Keeps every occupied region of every voice tiled, filling what is left with rests.

    Geometry reports holes without judging them; which holes deserve rests is decided
    here, and the two rules are deliberately NOT symmetric:

    * a measure the voice holds nothing in is **asleep** and is skipped, so an empty
      voice stays empty instead of sprouting rests;
    * a tuplet that exists has its interior occupied by definition, so it is **always**
      tiled in full and never sleeps.
    """

    def __init__(self) -> None:
        self._size_mapper: RhythmicSizeMapper = RhythmicSizeMapper()

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
    ) -> Sequence[CreateRestRequest]:
        if not document.measures:
            return []

        geometry: ScoreGeometry = ScoreGeometry(origin=document.measures[0])

        fill_requests: list[CreateRestRequest] = []
        for voice in document.voices:
            for scope, gap in self._gaps_of_voice(geometry=geometry, voice=voice):
                fill_requests.extend(
                    self._fill(geometry=geometry, voice=voice, scope=scope, gap=gap)
                )

        return fill_requests

    def _gaps_of_voice(
        self,
        *,
        geometry: ScoreGeometry,
        voice: Voice,
    ) -> list[tuple[Voice | GroupRhythmicContainer, Span]]:
        """Every hole of the voice, paired with the scope it lies in — the rest filling it
        is created right there, never re-derived."""
        return [
            *((voice, gap) for gap in self._measure_gaps(geometry=geometry, voice=voice)),
            *self._nested_gaps(geometry=geometry, scope=voice),
        ]

    def _measure_gaps(self, *, geometry: ScoreGeometry, voice: Voice) -> list[Span]:
        """Holes in the measures this voice actually reaches into."""
        contents: list[tuple[RhythmicContainer, Span]] = geometry.contents_of(scope=voice)
        covered: list[Span] = [span for _, span in contents]

        # THE SLEEPING RULE. A measure the voice holds nothing in is asleep, not empty: it
        # is not a bucket at all, so nothing fills it. What holds something is a leaf or a
        # group with children — an empty group is about to be cleaned up and wakes nothing.
        # Drop this filter and every silent measure of every voice sprouts rests.
        holding: list[Span] = [
            span
            for child, span in contents
            if not isinstance(child, GroupRhythmicContainer) or child.children
        ]
        awake: list[Span] = [
            region
            for _, region in geometry.measure_regions()
            if any(region.intersects(span) for span in holding)
        ]

        return [hole for bucket in awake for hole in gaps(bucket=bucket, covered=covered)]

    def _nested_gaps(
        self,
        *,
        geometry: ScoreGeometry,
        scope: Voice | GroupRhythmicContainer,
    ) -> list[tuple[Voice | GroupRhythmicContainer, Span]]:
        found: list[tuple[Voice | GroupRhythmicContainer, Span]] = []

        for child in scope.children:
            if not isinstance(child, GroupRhythmicContainer):
                continue
            # an empty group is never filled: the cleanup removes it at the gesture boundary
            if not child.children:
                continue

            covered: list[Span] = [span for _, span in geometry.contents_of(scope=child)]
            # no sleeping rule here, on purpose: the group's whole interior is one
            # bucket and it is always live while the group exists
            found.extend(
                (child, gap)
                for gap in gaps(
                    bucket=interior(frame=geometry.of_group(group=child)),
                    covered=covered,
                )
            )
            found.extend(self._nested_gaps(geometry=geometry, scope=child))

        return found

    def _fill(
        self,
        *,
        geometry: ScoreGeometry,
        voice: Voice,
        scope: Voice | GroupRhythmicContainer,
        gap: Span,
    ) -> list[CreateRestRequest]:
        # one gap, one staff: chosen once for every rest the gap is spelled into
        try:
            staff: Staff = resolve_staff(geometry=geometry, voice=voice, gap=gap)
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        try:
            mapped_sizes: list[DottedRhythmicValue] = self._size_mapper.spell_duration(
                duration=gap.length
            )
        except ValueError as error:
            raise MutationRejectedError(f"Cannot spell gap {gap.length} at {gap.start}.") from error

        requests: list[CreateRestRequest] = []

        offset: Fraction = Fraction(0)
        for mapped in mapped_sizes:
            piece: Span = Span(
                frame=gap.frame,
                start=gap.start + offset,
                length=mapped.fraction,
            )
            at: Point = piece.start_point.to(frame=geometry.root)

            measure: Measure | None = geometry.measure_at(point=at)
            if measure is None:
                # the lookup reports the fact; refusing the gesture is this
                # postprocessor's own call
                raise MutationRejectedError(f"Gap at {at.value} lies past the last measure.")

            position: MeasurePosition = MeasurePosition.of_fraction(
                fraction=at.to(frame=geometry.of_measure(measure=measure)).value,
            )

            requests.append(
                CreateRestRequest(
                    scope=scope,
                    staff=staff,
                    measure=measure,
                    position=position,
                    written_value=mapped,
                    out=ResultRef[Rest](),
                )
            )

            offset += mapped.fraction

        return requests
