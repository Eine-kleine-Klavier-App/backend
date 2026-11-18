from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.material import Note

from .pedal import PedalSpan
from .played import PlayedNote
from .timeline import Timeline


@dataclass(frozen=True, slots=True, kw_only=True)
class TimedNote:
    """A note to be played with its time in milliseconds from the start of the playback: the
    note it comes from (its carrier holds the marks), its MIDI number, attack, physical key
    release and end of sustain holding."""

    source: Note
    pitch: int
    start_ms: float
    key_release_ms: float
    end_ms: float


def time_notes(
    *,
    notes: Sequence[PlayedNote],
    timeline: Timeline,
    pedal: Sequence[PedalSpan],
) -> list[TimedNote]:
    """The notes in time. A note whose end falls inside a stretch of pedal keeps sounding until
    the pedal goes up; one that ends as the pedal goes down, or as it goes up, does not. The
    stretches lie in order and do not overlap, so the one an end falls into is the last that
    begins before it."""
    starts: list[Fraction] = [span.start for span in pedal]
    timed: list[TimedNote] = []
    for played in notes:
        end: Fraction = played.end
        index: int = bisect_left(starts, end) - 1
        if index >= 0 and end < pedal[index].end:
            end = pedal[index].end

        timed.append(
            TimedNote(
                source=played.source,
                pitch=played.pitch,
                start_ms=timeline.ms_at(position=played.start),
                key_release_ms=timeline.ms_at(position=played.end),
                end_ms=timeline.ms_at(position=end),
            )
        )

    return timed
