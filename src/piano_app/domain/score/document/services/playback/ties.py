from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.services.pitch import Pitch

from .errors import ProjectionError


@dataclass(frozen=True, slots=True, kw_only=True)
class SoundInterval:
    """Resolved musical interval before timing and attack interpretation."""

    pitch: Pitch
    start: Fraction
    end: Fraction
    voice_id: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ProjectionError("Sound interval must have a positive length.")
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        if not self.source_ids:
            raise ProjectionError("Sound interval needs a source.")


def merge_ties(
    *, intervals: Sequence[SoundInterval], links: Sequence[tuple[str, str]]
) -> tuple[SoundInterval, ...]:
    by_id: dict[str, SoundInterval] = {}
    for interval in intervals:
        if len(interval.source_ids) != 1 or interval.source_ids[0] in by_id:
            raise ProjectionError("Tie input needs unique single-source intervals.")
        by_id[interval.source_ids[0]] = interval
    outgoing: dict[str, str] = {}
    incoming: set[str] = set()
    for start, end in links:
        if start not in by_id or end not in by_id:
            raise ProjectionError("Tie refers to a missing source.")
        if start in outgoing or end in incoming:
            raise ProjectionError("Tie chain branches.")
        left, right = by_id[start], by_id[end]
        if left.end != right.start or left.pitch != right.pitch or left.voice_id != right.voice_id:
            raise ProjectionError("Tie must join adjacent equal pitches in one voice.")
        outgoing[start] = end
        incoming.add(end)
    result: list[SoundInterval] = []
    visited: set[str] = set()
    for source, first in by_id.items():
        if source in incoming:
            continue
        sources: list[str] = []
        current = source
        while True:
            if current in visited:
                raise ProjectionError("Tie chain contains a cycle.")
            visited.add(current)
            sources.append(current)
            last = by_id[current]
            if current not in outgoing:
                break
            current = outgoing[current]
        result.append(
            SoundInterval(
                pitch=first.pitch,
                start=first.start,
                end=last.end,
                voice_id=first.voice_id,
                source_ids=tuple(sources),
            )
        )
    if len(visited) != len(by_id):
        raise ProjectionError("Tie chain contains a cycle.")
    return tuple(sorted(result, key=lambda sound: (sound.start, sound.voice_id, sound.source_ids)))
