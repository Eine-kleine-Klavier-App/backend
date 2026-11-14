from fractions import Fraction
from itertools import pairwise

import pytest

from piano_app.domain.score.document.models.notation import Ornament
from piano_app.domain.score.document.services.playback import ORNAMENT_UNIT, Piece, ornament_pieces

# Times are in whole notes: a quarter is 1/4 and the short notes of an ornament are 1/32.

_U: Fraction = ORNAMENT_UNIT


def _shape(*, ornament: Ornament, length: Fraction, room: Fraction | None = None) -> list[tuple]:
    """(steps, length of the note) of each note of the expansion of a sound starting at 1."""
    pieces: list[Piece] = ornament_pieces(
        ornament=ornament,
        start=Fraction(1),
        end=1 + length,
        room=length if room is None else room,
    )
    assert pieces[0].start == 1
    assert pieces[-1].end == 1 + length
    for before, after in pairwise(pieces):
        assert before.end == after.start

    return [(piece.steps, piece.end - piece.start) for piece in pieces]


@pytest.mark.unit
def test_no_ornament_is_the_note_itself() -> None:
    assert _shape(ornament=Ornament.NONE, length=Fraction(1, 4)) == [(0, Fraction(1, 4))]


@pytest.mark.unit
def test_an_upper_mordent_on_a_quarter_is_two_short_notes_and_the_rest() -> None:
    assert _shape(ornament=Ornament.UPPER_MORDENT, length=Fraction(1, 4)) == [
        (0, _U),
        (1, _U),
        (0, Fraction(1, 4) - 2 * _U),
    ]


@pytest.mark.unit
def test_a_lower_mordent_goes_below() -> None:
    assert [
        steps for steps, _ in _shape(ornament=Ornament.LOWER_MORDENT, length=Fraction(1, 4))
    ] == [
        0,
        -1,
        0,
    ]


@pytest.mark.unit
def test_a_turn_is_the_upper_note_the_main_the_lower_and_the_main_again() -> None:
    shape: list[tuple] = _shape(ornament=Ornament.TURN, length=Fraction(1, 2))

    assert [steps for steps, _ in shape] == [1, 0, -1, 0]
    assert [length for _, length in shape[:3]] == [_U, _U, _U]


@pytest.mark.unit
def test_an_inverted_turn_goes_the_other_way_round() -> None:
    assert [
        steps for steps, _ in _shape(ornament=Ornament.INVERTED_TURN, length=Fraction(1, 2))
    ] == [
        -1,
        0,
        1,
        0,
    ]


@pytest.mark.unit
def test_the_short_notes_of_a_mordent_on_a_32nd_share_the_room() -> None:
    """The whole sound is one unit: each of the three notes takes a third of it."""
    shape: list[tuple] = _shape(ornament=Ornament.UPPER_MORDENT, length=_U)

    assert [length for _, length in shape] == [_U / 3, _U / 3, _U / 3]


@pytest.mark.unit
def test_the_room_of_the_shortest_note_of_a_chord_limits_the_short_notes() -> None:
    """A long sound whose chord has a short note: the short notes follow the room, the last
    note still goes to the end of its own sound."""
    shape: list[tuple] = _shape(
        ornament=Ornament.UPPER_MORDENT,
        length=Fraction(1, 2),
        room=_U,
    )

    assert [length for _, length in shape[:2]] == [_U / 3, _U / 3]
    assert shape[2][1] == Fraction(1, 2) - 2 * (_U / 3)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("length", "short_notes"),
    [
        (Fraction(1, 2), 14),
        (Fraction(1, 4), 6),
        (Fraction(1, 8), 2),
        (3 * _U, 2),
        (2 * _U, 0),
        (_U, 0),
    ],
)
def test_a_trill_alternates_two_notes_and_ends_on_the_main_one(
    length: Fraction, short_notes: int
) -> None:
    shape: list[tuple] = _shape(ornament=Ornament.TRILL, length=length)

    assert len(shape) == short_notes + 1
    assert [steps for steps, _ in shape] == [index % 2 for index in range(short_notes)] + [0]
    assert all(piece_length == _U for _, piece_length in shape[:-1])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ornament", "length", "strikes", "unit"),
    [
        (Ornament.TREMOLO_3, Fraction(1, 4), 8, Fraction(1, 32)),
        (Ornament.TREMOLO_2, Fraction(3, 8), 6, Fraction(1, 16)),
        (Ornament.TREMOLO_1, Fraction(1, 4), 2, Fraction(1, 8)),
    ],
)
def test_a_tremolo_strikes_the_main_note_again_every_unit_of_its_strokes(
    ornament: Ornament, length: Fraction, strikes: int, unit: Fraction
) -> None:
    shape: list[tuple] = _shape(ornament=ornament, length=length)

    assert shape == [(0, unit)] * strikes


@pytest.mark.unit
def test_a_tremolo_longer_than_its_note_is_a_plain_note() -> None:
    assert _shape(ornament=Ornament.TREMOLO_1, length=Fraction(1, 16)) == [(0, Fraction(1, 16))]


@pytest.mark.unit
def test_the_last_strike_of_a_tremolo_takes_what_the_whole_units_leave() -> None:
    assert _shape(ornament=Ornament.TREMOLO_1, length=Fraction(3, 16)) == [(0, Fraction(3, 16))]
    assert _shape(ornament=Ornament.TREMOLO_3, length=Fraction(1, 4), room=Fraction(1, 8)) == [
        (0, _U),
        (0, _U),
        (0, _U),
        (0, Fraction(5, 32)),
    ]
