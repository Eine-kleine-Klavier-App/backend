from dataclasses import dataclass
from math import isfinite

from piano_app.domain.score.document.services.pitch import Pitch

from .errors import ProjectionError


@dataclass(frozen=True, slots=True, kw_only=True)
class Sound:
    """One attack and its holding time, independent of the synthesizer's release tail."""

    pitch: Pitch
    onset_ms: float
    duration_ms: float
    velocity: int
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isfinite(self.onset_ms) or self.onset_ms < 0:
            raise ProjectionError("Sound onset must be finite and nonnegative.")
        if not isfinite(self.duration_ms) or self.duration_ms <= 0:
            raise ProjectionError("Sound duration must be finite and positive.")
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ProjectionError("Attack velocity must be an integer in 1..127.")
        object.__setattr__(self, "source_ids", tuple(self.source_ids))


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackProjection:
    """An immutable snapshot, including time in which nothing sounds."""

    sounds: tuple[Sound, ...]
    extent_ms: float

    def __post_init__(self) -> None:
        if not isfinite(self.extent_ms) or self.extent_ms < 0:
            raise ProjectionError("Projection extent must be finite and nonnegative.")
        object.__setattr__(self, "sounds", tuple(self.sounds))
        previous = -1.0
        for sound in self.sounds:
            if sound.onset_ms < previous:
                raise ProjectionError("Sounds must be ordered by onset.")
            previous = sound.onset_ms
            # A duration obtained by subtracting two times may round on addition.
            if sound.onset_ms + sound.duration_ms > self.extent_ms + 1e-9:
                raise ProjectionError("Sound lies beyond the projection extent.")
