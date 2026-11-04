from bisect import bisect_right
from collections.abc import Sequence
from fractions import Fraction
from functools import partial

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import DynamicChange, Hairpin
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .route import RouteSegment
from .track import Change, Region, walk_route

_LOUDEST: Fraction = Fraction(len(DynamicMarking) - 1)


def _after_hairpin(steps: int, origin: Fraction) -> Fraction:
    """The level a hairpin ends at: its steps from the level it starts at, held to the scale."""
    return min(max(origin + steps, Fraction(0)), _LOUDEST)


class Dynamics:
    """The dynamic level of each voice in the time of the route, from 0 (the softest marking)
    to the loudest, with fractions inside a hairpin."""

    def __init__(self, *, regions: dict[Voice, list[Region]]) -> None:
        self._regions: dict[Voice, list[Region]] = regions
        self._starts: dict[Voice, list[Fraction]] = {
            voice: [region.start for region in voice_regions]
            for voice, voice_regions in regions.items()
        }

    def level_at(self, *, voice: Voice, position: Fraction) -> float:
        """The level of the voice at a position of the route: what a note struck there gets."""
        regions: list[Region] = self._regions[voice]
        if not regions or not regions[0].start <= position <= regions[-1].end:
            raise ValueError("The position lies outside the played score.")

        index: int = min(bisect_right(self._starts[voice], position) - 1, len(regions) - 1)
        region: Region = regions[index]
        progress: Fraction = (position - region.start) / (region.end - region.start)

        return float(region.start_value + (region.end_value - region.start_value) * progress)


def build_dynamics(
    *,
    document: ScoreDocument,
    route: Sequence[RouteSegment],
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> Dynamics:
    """The dynamics of every voice along the route, read as ``walk_route`` reads a value: a
    dynamic carries over a jump as it is, a hairpin a jump cuts off keeps the level it
    reached."""
    regions: dict[Voice, list[Region]] = {}
    for voice in document.voices:
        scope: Scope = Scope.of_voice(voice=voice)
        points: list[tuple[Fraction, Fraction]] = []
        for point in contexts.contexts_of(kind=DynamicChange, scope=scope):
            points.append(
                (geometry.point_of(anchor=point.start).value, Fraction(point.dynamic.level))
            )

        changes: list[Change] = []
        for hairpin in contexts.contexts_of(kind=Hairpin, scope=scope):
            changes.append(
                Change(
                    start=geometry.point_of(anchor=hairpin.start).value,
                    end=geometry.end_of(context=hairpin).value,
                    end_value=partial(_after_hairpin, hairpin.steps),
                )
            )

        regions[voice] = walk_route(route=route, points=points, changes=changes, name="dynamic")

    return Dynamics(regions=regions)
