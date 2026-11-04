from bisect import bisect_right
from collections.abc import Sequence
from fractions import Fraction
from functools import partial
from math import log
from operator import mul

from piano_app.domain.score.document.models.context import TempoChange, TempoTransition
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .route import RouteSegment
from .track import Change, Region, walk_route

_MS_PER_MINUTE: int = 60000


class Timeline:
    """The milliseconds of the time of the route: the played score in whole notes to time."""

    def __init__(self, *, regions: Sequence[Region]) -> None:
        self._regions: tuple[Region, ...] = tuple(regions)
        self._starts: list[Fraction] = [region.start for region in regions]
        self._totals: list[float] = [0.0]
        for region in regions:
            self._totals.append(self._totals[-1] + _elapsed(region=region, progress=Fraction(1)))

    @property
    def regions(self) -> tuple[Region, ...]:
        """The stretches the time is made of: over each the speed goes linearly, in position,
        from one value to another."""
        return self._regions

    @property
    def extent(self) -> Fraction:
        return self._regions[-1].end if self._regions else Fraction(0)

    def ms_at(self, *, position: Fraction) -> float:
        """The time, in milliseconds from the start, at a position of the route."""
        if not 0 <= position <= self.extent:
            raise ValueError("The position lies outside the played score.")

        if position == self.extent:
            return self._totals[-1]

        index: int = bisect_right(self._starts, position) - 1
        region: Region = self._regions[index]
        progress: Fraction = (position - region.start) / (region.end - region.start)

        return self._totals[index] + _elapsed(region=region, progress=progress)


def _elapsed(*, region: Region, progress: Fraction) -> float:
    """The milliseconds that go by over the first ``progress`` of a region."""
    length: Fraction = region.end - region.start
    if region.start_value == region.end_value:
        return float(_MS_PER_MINUTE * length * progress / region.start_value)

    difference: Fraction = region.end_value - region.start_value

    return float(_MS_PER_MINUTE * length / difference) * log(
        1 + float(difference * progress / region.start_value)
    )


def build_timeline(
    *,
    route: Sequence[RouteSegment],
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> Timeline:
    """The timeline of the tempo along the route, read as ``walk_route`` reads a value: the
    tempo carries over a jump, a gradual change a jump cuts off keeps the speed it reached.
    The speed is in whole notes per minute, the beat unit of each tempo taken into account.
    """
    points: list[tuple[Fraction, Fraction]] = []
    for point in contexts.contexts_of(kind=TempoChange, scope=Scope.score()):
        points.append(
            (geometry.point_of(anchor=point.start).value, Fraction(point.bpm) * point.beat.fraction)
        )

    changes: list[Change] = []
    for transition in contexts.contexts_of(kind=TempoTransition, scope=Scope.score()):
        changes.append(
            Change(
                start=geometry.point_of(anchor=transition.start).value,
                end=geometry.end_of(context=transition).value,
                end_value=partial(mul, transition.ratio),
            )
        )

    return Timeline(regions=walk_route(route=route, points=points, changes=changes, name="tempo"))
