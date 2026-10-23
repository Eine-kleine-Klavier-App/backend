from bisect import bisect_right
from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.services.geometry import Frame, Point, Span

from .errors import PitchResolutionError
from .regions import OctaveRegion, PitchRegion
from .transform import PitchTransform
from .values import Pitch


class PitchResolver:
    """Resolve numeric pitch inputs against a snapshot of temporal rules.

    Rule ranges are exclusive; additive octave ranges may overlap. All coordinates
    are normalized once to the supplied frame, with binary searches on each read.
    """

    def __init__(
        self,
        *,
        frame: Frame,
        regions: Sequence[PitchRegion],
        octave_regions: Sequence[OctaveRegion] = (),
    ) -> None:
        self._frame: Frame = frame
        self._regions: tuple[PitchRegion, ...] = tuple(
            sorted(
                (
                    PitchRegion(span=self._normalize(region.span), transform=region.transform)
                    for region in regions
                ),
                key=lambda region: region.span.start,
            )
        )
        for left, right in zip(self._regions, self._regions[1:], strict=False):
            if left.span.end > right.span.start:
                raise PitchResolutionError("Pitch rule regions must not overlap.")
        self._starts: tuple[Fraction, ...] = tuple(region.span.start for region in self._regions)

        changes: dict[Fraction, int] = {}
        for region in octave_regions:
            span: Span = self._normalize(region.span)
            changes[span.start] = changes.get(span.start, 0) + region.octaves
            changes[span.end] = changes.get(span.end, 0) - region.octaves
        self._shift_positions: tuple[Fraction, ...] = tuple(sorted(changes))
        shifts: list[int] = []
        total: int = 0
        for position in self._shift_positions:
            total += changes[position]
            shifts.append(total)
        self._shifts: tuple[int, ...] = tuple(shifts)

    def resolve(self, *, point: Point, staff_step: int, accidental: int) -> Pitch:
        transform, octaves = self._rules_at(point=point)
        return transform.resolve(staff_step=staff_step, accidental=accidental, octaves=octaves)

    def staff_step_for(self, *, point: Point, midi_note: int, accidental: int) -> int:
        """The staff step that sounds ``midi_note`` with the accidental at the point."""
        transform, octaves = self._rules_at(point=point)
        return transform.staff_step_for(midi_note=midi_note, accidental=accidental, octaves=octaves)

    def _rules_at(self, *, point: Point) -> tuple[PitchTransform, int]:
        """The rule covering the point and the sum of the octave shifts over it."""
        position: Fraction = point.to(frame=self._frame).value
        if not 0 <= position < self._frame.extent:
            raise PitchResolutionError("Pitch point is outside the timeline.")

        index: int = bisect_right(self._starts, position) - 1
        if index < 0 or position >= self._regions[index].span.end:
            raise PitchResolutionError("No pitch rule covers the point.")

        shift_index: int = bisect_right(self._shift_positions, position) - 1
        octaves: int = self._shifts[shift_index] if shift_index >= 0 else 0
        return self._regions[index].transform, octaves

    def _normalize(self, span: Span) -> Span:
        normalized: Span = span.to(frame=self._frame)
        if normalized.start < 0 or normalized.end > self._frame.extent:
            raise PitchResolutionError("Pitch region is outside the timeline.")
        return normalized
