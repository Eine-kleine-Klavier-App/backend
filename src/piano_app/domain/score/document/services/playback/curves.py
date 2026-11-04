from dataclasses import dataclass
from fractions import Fraction
from math import exp, floor, isfinite, log, log1p

from .errors import ProjectionError


@dataclass(frozen=True, slots=True, kw_only=True)
class DynamicCurve:
    """Configurable S-curve; the approach, not Dorico's proprietary implementation."""

    min_level: float = 0
    max_level: float = 7
    min_velocity: int = 16
    max_velocity: int = 126
    power: float = 2

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.min_level, self.max_level, self.power)):
            raise ProjectionError("Curve parameters must be finite.")
        if (
            self.min_level >= self.max_level
            or self.power <= 0
            or not isfinite(self.max_level - self.min_level)
        ):
            raise ProjectionError("Curve needs increasing level bounds and positive power.")
        if (
            type(self.min_velocity) is not int
            or type(self.max_velocity) is not int
            or not 1 <= self.min_velocity <= self.max_velocity <= 127
        ):
            raise ProjectionError("Curve velocities must be ordered integers in 1..127.")

    def velocity_at(self, *, level: float) -> int:
        if not isfinite(level):
            raise ProjectionError("Dynamic level must be finite.")
        if level <= self.min_level:
            return self.min_velocity
        if level >= self.max_level:
            return self.max_velocity
        x = (level - self.min_level) / (self.max_level - self.min_level)
        if x <= 0:
            return self.min_velocity
        if x >= 1:
            return self.max_velocity
        # x**power / (x**power + (1-x)**power), stable for large powers.
        odds = self.power * (log1p(-x) - log(x))
        shaped = exp(-odds) / (1 + exp(-odds)) if odds >= 0 else 1 / (1 + exp(odds))
        return floor(self.min_velocity + (self.max_velocity - self.min_velocity) * shaped + 0.5)


@dataclass(frozen=True, slots=True)
class LinearDynamicInterpolation:
    def level_at(self, *, start: float, end: float, progress: Fraction) -> float:
        if not all(isfinite(v) for v in (start, end)) or not 0 <= progress <= 1:
            raise ProjectionError("Invalid dynamic interpolation arguments.")
        if progress == 0:
            return start
        if progress == 1:
            return end
        return start * (1 - float(progress)) + end * float(progress)


@dataclass(frozen=True, slots=True)
class LinearTempoInterpolation:
    """Speed is linear in musical position; elapsed time integrates its reciprocal."""

    def elapsed_ms(
        self,
        *,
        start_speed: Fraction,
        end_speed: Fraction,
        length: Fraction,
        progress: Fraction,
    ) -> float:
        if min(start_speed, end_speed) <= 0 or length <= 0 or not 0 <= progress <= 1:
            raise ProjectionError("Invalid tempo interpolation arguments.")
        if progress == 0:
            return 0.0
        delta = end_speed - start_speed
        if delta == 0:
            return float(60000 * length * progress / start_speed)
        relative = float(delta * progress / start_speed)
        logarithm = (
            log1p(relative)
            if relative > -1
            else log(float((start_speed + delta * progress) / start_speed))
        )
        elapsed = float(60000 * length / delta) * logarithm
        if not isfinite(elapsed) or elapsed <= 0:
            raise ProjectionError("Tempo interpolation produced invalid time.")
        return elapsed
