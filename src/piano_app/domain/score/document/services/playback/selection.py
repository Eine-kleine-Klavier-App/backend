from dataclasses import replace
from math import isfinite

from .errors import ProjectionError
from .values import PlaybackProjection


def select_fragment(
    *,
    projection: PlaybackProjection,
    start_ms: float,
    end_ms: float,
) -> PlaybackProjection:
    """Re-attack intersecting holds at zero, preserving velocity and remaining duration."""
    if not all(isfinite(t) for t in (start_ms, end_ms)) or not (
        0 <= start_ms <= end_ms <= projection.extent_ms
    ):
        raise ProjectionError("Selection must lie within the projection.")
    sounds = []
    for sound in projection.sounds:
        start = max(start_ms, sound.onset_ms)
        end = min(end_ms, sound.onset_ms + sound.duration_ms)
        if start < end:
            sounds.append(replace(sound, onset_ms=start - start_ms, duration_ms=end - start))
    return PlaybackProjection(sounds=tuple(sounds), extent_ms=end_ms - start_ms)
