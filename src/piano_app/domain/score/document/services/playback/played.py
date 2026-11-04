from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.material import Note

# The length of the short notes of an ornament and the step of an arpeggio, a note value (a
# 32nd of a whole note): in the time of the route, never in seconds (owner, 2026-11-07).
ORNAMENT_UNIT: Fraction = Fraction(1, 32)

# The share of its note's own stretch, counted from the end, that a glissando's steps take; the note
# sounds as itself before (owner, 2026-11-09).
GLISSANDO_SHARE: Fraction = Fraction(1, 2)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayedNote:
    """A plain note to be played: the note it comes from (its carrier holds the marks), its
    MIDI number and where it starts and ends in the time of the route."""

    source: Note
    pitch: int
    start: Fraction
    end: Fraction
