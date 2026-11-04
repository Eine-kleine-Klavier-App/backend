from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, floor, isfinite, log, log1p

from piano_app.domain.score.document.models.notation import Articulation
from piano_app.domain.score.document.services.helpers import host_leaf_of, voice_of

from .dynamics import Dynamics
from .played import PlayedNote

# How many dynamic levels louder a mark of loudness makes a note (owner, 2026-11-07: to be
# looked at in practice), a row to change.
LOUDNESS_BOOST: dict[Articulation, int] = {
    Articulation.ACCENT: 1,
    Articulation.MARCATO: 2,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class DynamicCurve:
    """The velocity of a note struck at a dynamic level: an S-curve between the softest and the
    loudest level, ``x**power / (x**power + (1 - x)**power)`` of the way from the lowest to the
    highest velocity, rounded half up (the piano profile of 2026-10-25: levels 0 to 7, velocities
    16 to 126, power 2; the approach of Dorico, not its formula)."""

    min_level: float = 0
    max_level: float = 7
    min_velocity: int = 16
    max_velocity: int = 126
    power: float = 2

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.min_level, self.max_level, self.power)):
            raise ValueError("The curve parameters must be finite.")

        if self.min_level >= self.max_level or self.power <= 0:
            raise ValueError("The curve needs increasing level bounds and a positive power.")

        if not 1 <= self.min_velocity <= self.max_velocity <= 127:
            raise ValueError("The curve velocities must be ordered integers in 1 to 127.")

    def velocity_at(self, *, level: float) -> int:
        if not isfinite(level):
            raise ValueError("A dynamic level must be finite.")

        if level <= self.min_level:
            return self.min_velocity

        if level >= self.max_level:
            return self.max_velocity

        x: float = (level - self.min_level) / (self.max_level - self.min_level)
        odds: float = self.power * (log1p(-x) - log(x))
        shaped: float = exp(-odds) / (1 + exp(-odds)) if odds >= 0 else 1 / (1 + exp(odds))

        return floor(self.min_velocity + (self.max_velocity - self.min_velocity) * shaped + 0.5)


# the piano profile, the curve a playback is built with unless it is given another
PIANO_CURVE: DynamicCurve = DynamicCurve()


def velocities(
    *,
    notes: Sequence[PlayedNote],
    dynamics: Dynamics,
    curve: DynamicCurve,
) -> list[int]:
    """The velocity of each note: the level of its voice where it starts (the voice of its
    leaf, for a grace note the leaf it belongs to), raised by the mark of loudness of its
    carrier, through the curve. The level is read at the attack only: a held note keeps it."""
    result: list[int] = []
    for played in notes:
        leaf = host_leaf_of(note=played.source)
        if leaf is None:
            raise ValueError("The note does not stand in a metric leaf.")

        level: float = dynamics.level_at(voice=voice_of(leaf), position=played.start)
        for mark, boost in LOUDNESS_BOOST.items():
            if mark in played.source.note_carrier.articulations:
                level += boost

        result.append(curve.velocity_at(level=level))

    return result
