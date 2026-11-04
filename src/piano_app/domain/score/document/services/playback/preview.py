from collections.abc import Sequence
from math import isfinite

from piano_app.domain.score.document.services.pitch import Pitch

from .errors import ProjectionError
from .values import PlaybackProjection, Sound


def preview_chord(
    *,
    pitches: Sequence[Pitch],
    velocity: int,
    duration_ms: float = 650,
    source_ids: Sequence[str] | None = None,
) -> PlaybackProjection:
    """A simultaneous fixed-duration audition of already resolved pitches."""
    if not isfinite(duration_ms) or duration_ms <= 0:
        raise ProjectionError("Preview duration must be finite and positive.")
    if type(velocity) is not int or not 1 <= velocity <= 127:
        raise ProjectionError("Preview velocity must be an integer in 1..127.")
    if source_ids is not None and len(source_ids) != len(pitches):
        raise ProjectionError("Each preview pitch needs its own source ID.")
    return PlaybackProjection(
        sounds=tuple(
            Sound(
                pitch=pitch,
                onset_ms=0,
                duration_ms=duration_ms,
                velocity=velocity,
                source_ids=() if source_ids is None else (source_ids[index],),
            )
            for index, pitch in enumerate(pitches)
        ),
        extent_ms=duration_ms,
    )
