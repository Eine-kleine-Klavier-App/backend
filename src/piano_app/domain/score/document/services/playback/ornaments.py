from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.notation import Ornament

from .played import ORNAMENT_UNIT


@dataclass(frozen=True, slots=True, kw_only=True)
class Piece:
    """A note of an expanded ornament: how many staff steps above the main note it stands
    (below when negative) and where it starts and ends."""

    steps: int
    start: Fraction
    end: Fraction


# The staff steps of the notes of each ornament, in order; the last takes what is left of the
# sound, the others are short.
_PROFILES: dict[Ornament, tuple[int, ...]] = {
    Ornament.UPPER_MORDENT: (0, 1, 0),
    Ornament.LOWER_MORDENT: (0, -1, 0),
    Ornament.TURN: (1, 0, -1, 0),
    Ornament.INVERTED_TURN: (-1, 0, 1, 0),
}

# The note value a tremolo repeats its note in, by its number of strokes: each stroke halves it.
_TREMOLO_UNITS: dict[Ornament, Fraction] = {
    Ornament.TREMOLO_1: Fraction(1, 8),
    Ornament.TREMOLO_2: Fraction(1, 16),
    Ornament.TREMOLO_3: Fraction(1, 32),
}


def ornament_pieces(
    *,
    ornament: Ornament,
    start: Fraction,
    end: Fraction,
    room: Fraction,
) -> list[Piece]:
    """The notes an ornament is played as, from ``start`` to ``end``.

    ``room`` is the time the short notes may take together: the shortest sounding length of
    the new notes of the carrier. A short note lasts a unit, or the room shared by the notes
    of the ornament when that is less, and the last note lasts to ``end``. A trill alternates
    the main note and the one above for as long as the room holds whole units, always ending
    on the main note; with less than three units it is a plain note. A tremolo strikes the main
    note again every unit of its strokes for as many whole units as the room holds, the last
    strike lasting to ``end``; a room shorter than one unit is a plain note.
    """
    if ornament is Ornament.NONE:
        return [Piece(steps=0, start=start, end=end)]

    if ornament in _TREMOLO_UNITS:
        tremolo_unit: Fraction = _TREMOLO_UNITS[ornament]
        strikes: int = max(1, room // tremolo_unit)
        tremolo: list[Piece] = [
            Piece(
                steps=0,
                start=start + index * tremolo_unit,
                end=start + (index + 1) * tremolo_unit,
            )
            for index in range(strikes - 1)
        ]
        tremolo.append(Piece(steps=0, start=start + (strikes - 1) * tremolo_unit, end=end))

        return tremolo

    if ornament is Ornament.TRILL:
        units: int = room // ORNAMENT_UNIT
        short_notes: int = max(0, units - 1) // 2 * 2
        pieces: list[Piece] = []
        for index in range(short_notes):
            pieces.append(
                Piece(
                    steps=index % 2,
                    start=start + index * ORNAMENT_UNIT,
                    end=start + (index + 1) * ORNAMENT_UNIT,
                )
            )

        pieces.append(Piece(steps=0, start=start + short_notes * ORNAMENT_UNIT, end=end))

        return pieces

    steps: tuple[int, ...] = _PROFILES[ornament]
    length: Fraction = min(ORNAMENT_UNIT, room / len(steps))
    pieces = []
    cursor: Fraction = start
    for step in steps[:-1]:
        pieces.append(Piece(steps=step, start=cursor, end=cursor + length))
        cursor += length

    pieces.append(Piece(steps=steps[-1], start=cursor, end=end))

    return pieces
