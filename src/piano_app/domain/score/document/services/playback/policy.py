from dataclasses import dataclass
from fractions import Fraction
from typing import Protocol

from .curves import DynamicCurve, LinearDynamicInterpolation, LinearTempoInterpolation


class VelocityCurve(Protocol):
    """A configured dynamic-level curve, including bounds and integer rounding."""

    def velocity_at(self, *, level: float) -> int: ...


class DynamicInterpolation(Protocol):
    """Interpolate levels at a normalized musical position, preserving endpoints."""

    def level_at(self, *, start: float, end: float, progress: Fraction) -> float: ...


class TempoInterpolation(Protocol):
    """Cumulative milliseconds from the start of a gradual tempo region.

    Speeds are whole notes per minute; length is in whole notes. Progress is the
    fraction of that musical length elapsed, in [0, 1]. The result starts at zero
    and is strictly increasing. Implementations integrate inverse speed according
    to their chosen curve; they must not multiply by the tempo at the query point.
    """

    def elapsed_ms(
        self,
        *,
        start_speed: Fraction,
        end_speed: Fraction,
        length: Fraction,
        progress: Fraction,
    ) -> float: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackPolicy:
    velocity_curve: VelocityCurve
    dynamic_interpolation: DynamicInterpolation
    tempo_interpolation: TempoInterpolation

    @classmethod
    def piano(cls) -> PlaybackPolicy:
        return cls(
            velocity_curve=DynamicCurve(),
            dynamic_interpolation=LinearDynamicInterpolation(),
            tempo_interpolation=LinearTempoInterpolation(),
        )
