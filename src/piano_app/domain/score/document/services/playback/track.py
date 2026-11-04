from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .route import RouteSegment

# at one position a gradual change that ends there is over before a point there takes over,
# and one that starts there starts from what a point there says
_ENDS: int = 0
_POINT: int = 1
_STARTS: int = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class Region:
    """A stretch of the time of the route over which a value (a speed, a dynamic level) goes
    linearly, in position, from one number to another."""

    start: Fraction
    end: Fraction
    start_value: Fraction
    end_value: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class Change:
    """A gradual change over a stretch of the score: where it starts and ends, and the value it
    ends at, given the value it starts from."""

    start: Fraction
    end: Fraction
    end_value: Callable[[Fraction], Fraction]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Active:
    """A gradual change in progress: the value it began from and the one it ends at."""

    change: Change
    origin: Fraction
    target: Fraction

    def value_at(self, *, position: Fraction) -> Fraction:
        progress: Fraction = (position - self.change.start) / (self.change.end - self.change.start)
        return self.origin + (self.target - self.origin) * progress


def walk_route(
    *,
    route: Sequence[RouteSegment],
    points: Sequence[tuple[Fraction, Fraction]],
    changes: Sequence[Change],
    name: str,
) -> list[Region]:
    """The value of something that is set at points of the score and changes gradually between
    others (a tempo, the dynamic of a voice), along the route, in the time of the route.

    The score is read in the order it is played, so a value carries over a jump as it is: a
    point holds until the next one, wherever the route has come from. A gradual change that a
    jump cuts off keeps the value it had reached; one begun before a stretch of the route is
    not resumed in it, and the next pass through its start begins it again from the value then
    in force. ``name`` is what the value is called in an error.
    """
    events: list[tuple[Fraction, int, Fraction | Change]] = []
    for position, point in points:
        events.append((position, _POINT, point))

    for change in changes:
        events.append((change.start, _STARTS, change))
        events.append((change.end, _ENDS, change))

    events.sort(key=lambda event: (event[0], event[1]))

    regions: list[Region] = []
    offset: Fraction = Fraction(0)
    value: Fraction | None = None
    active: _Active | None = None
    for segment in route:
        cursor: Fraction = segment.start
        for position, order, payload in events:
            if order == _ENDS:
                if not segment.start < position <= segment.end:
                    continue
            elif not segment.start <= position < segment.end:
                continue

            if position > cursor:
                if value is None:
                    raise ValueError(f"No {name} is in force.")

                regions.append(
                    Region(
                        start=offset + cursor - segment.start,
                        end=offset + position - segment.start,
                        start_value=value if active is None else active.value_at(position=cursor),
                        end_value=value if active is None else active.value_at(position=position),
                    )
                )

            cursor = position
            if isinstance(payload, Change):
                if order == _STARTS:
                    if value is None:
                        raise ValueError(f"No {name} is in force before a gradual change.")

                    active = _Active(
                        change=payload,
                        origin=value,
                        target=payload.end_value(value),
                    )
                elif active is not None and active.change is payload:
                    value = active.target
                    active = None
            else:
                value = payload

        if segment.end > cursor:
            if value is None:
                raise ValueError(f"No {name} is in force.")

            regions.append(
                Region(
                    start=offset + cursor - segment.start,
                    end=offset + segment.end - segment.start,
                    start_value=value if active is None else active.value_at(position=cursor),
                    end_value=value if active is None else active.value_at(position=segment.end),
                )
            )

        if active is not None:
            value = active.value_at(position=segment.end)
            active = None

        offset += segment.end - segment.start

    return regions
