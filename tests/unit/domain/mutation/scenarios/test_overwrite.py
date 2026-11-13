from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.compiler import TieNotesIntent

from ...scene import (
    NEW_STEP,
    Piano,
    Score,
    Slot,
    TieSlot,
    apply_intent,
    build_piano,
    build_score,
    crossing_half,
    eighth_triplet,
    group_layout,
    insert_note,
    layout,
    note,
    note_at,
    orphan_anchors,
    quarters,
    slot,
    tie_layout,
)

# Overwrite is decided per element (axis-levels-and-generator-analyzers, 2026-10-18): the new
# item is cut at barlines; when every piece lands exactly on an existing element of the same
# span, the new notes join those elements as a chord and the old pieces and ties stay;
# otherwise every element met is removed with its ties, and only those.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)


def _half_in_one_measure() -> Score:
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, step=1)

    return score


def _three_quarters() -> list[Slot]:
    return [slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)]


# --- a. a longer item over a crossing pair ------------------------------------------------


@pytest.mark.unit
def test_a_dotted_half_over_a_crossing_half_replaces_both_pieces() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "9"),
        slot(1, Fraction(0), _H, "9"),
        slot(1, _H, _H, "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 9), end=(1, Fraction(0), 9))
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_dotted_half_over_a_half_in_one_measure_replaces_it() -> None:
    score: Score = _half_in_one_measure()

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(3, 4), "9"),
        slot(0, Fraction(3, 4), _Q, "rest"),
    ]
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


# --- b. the same item over a crossing pair ------------------------------------------------


@pytest.mark.unit
def test_the_same_half_over_a_crossing_half_joins_both_pieces() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "1,9"),
        slot(1, Fraction(0), _Q, "1,9"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(0, Fraction(3, 4), 9), end=(1, Fraction(0), 9)),
    ]
    assert orphan_anchors(score=score) == []


# --- c. an item landing on one piece ------------------------------------------------------


@pytest.mark.unit
def test_a_quarter_on_the_first_piece_joins_it_and_keeps_the_tie() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "1,9"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1))
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_quarter_on_the_second_piece_joins_it_and_keeps_the_tie() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(1), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "1"),
        slot(1, Fraction(0), _Q, "1,9"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1))
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_quarter_over_a_half_in_one_measure_replaces_it() -> None:
    score: Score = _half_in_one_measure()

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "9"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_an_eighth_on_the_first_piece_removes_it_and_leaves_the_second_untied() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _E, "9"),
        slot(0, Fraction(7, 8), _E, "rest"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


# --- d, e. one piece matches, another does not --------------------------------------------


@pytest.mark.unit
def test_a_dotted_half_whose_tail_alone_matches_removes_everything_it_meets() -> None:
    """Cut h | q, only the tail lands on an element of its span.

    Quarters on beats 1-2, a quarter (step 2) on beat 3, the crossing half (step 1) on
    beat 4; the dotted half goes on beat 3.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF, step=1)
    insert_note(score=score, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=2)

    insert_note(score=score, at=_H, rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "9"),
        slot(1, Fraction(0), _Q, "9"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == [TieSlot(start=(0, _H, 9), end=(1, Fraction(0), 9))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_whole_whose_head_alone_matches_removes_everything_it_meets() -> None:
    score: Score = crossing_half()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.WHOLE)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "9"),
        slot(1, Fraction(0), Fraction(3, 4), "9"),
        slot(1, Fraction(3, 4), _Q, "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 9), end=(1, Fraction(0), 9))
    ]
    assert orphan_anchors(score=score) == []


# --- f. a cut spelled in several values ---------------------------------------------------


@pytest.mark.unit
def test_a_whole_over_eighths_removes_every_eighth_it_meets() -> None:
    """Spell the first cut half + eighth; only the eighth lands on an element of its span.

    Two measures of eighths; the whole at 3/8 is cut 5/8 | 3/8.
    """
    score: Score = build_score(measure_count=2)
    for index in range(16):
        note(
            score=score,
            parent=score.voice,
            at=Fraction(index, 8),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=0,
        )

    insert_note(score=score, at=Fraction(3, 8), rhythmic_value=RhythmicValue.WHOLE)

    assert layout(score=score) == [
        *[slot(0, Fraction(index, 8), _E, "0") for index in range(3)],
        slot(0, Fraction(3, 8), _H, "9"),
        slot(0, Fraction(7, 8), _E, "9"),
        slot(1, Fraction(0), Fraction(3, 8), "9"),
        *[slot(1, Fraction(index, 8), _E, "0") for index in range(3, 8)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 8), 9), end=(0, Fraction(7, 8), 9)),
        TieSlot(start=(0, Fraction(7, 8), 9), end=(1, Fraction(0), 9)),
    ]
    assert orphan_anchors(score=score) == []


# --- g. a tied pair inside one measure ----------------------------------------------------


@pytest.mark.unit
def test_a_half_over_two_tied_quarters_replaces_both() -> None:
    """Treat the tie as a modifier between two elements, not one element of a half's span."""
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=1)
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=Fraction(0)).id,
            end_note_id=note_at(score=score, at=_Q).id,
        ),
    )

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, step=NEW_STEP)

    assert layout(score=score) == [
        slot(0, Fraction(0), _H, "9"),
        slot(0, _H, _H, "rest"),
    ]
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


# --- h. a piece meeting a group -----------------------------------------------------------


@pytest.mark.unit
def test_a_half_whose_tail_meets_a_triplet_removes_everything_it_meets() -> None:
    """Remove the quarter on beat 4 and the triplet at the next barline as whole elements."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    eighth_triplet(score=score, parent=score.voice, at=Fraction(1))
    quarters(score=score, measure=1, beats=(1, 2, 3))

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        *_three_quarters(),
        slot(0, Fraction(3, 4), _Q, "9"),
        slot(1, Fraction(0), _Q, "9"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 9), end=(1, Fraction(0), 9))
    ]
    assert orphan_anchors(score=score) == []


# --- i. two staffs ------------------------------------------------------------------------


def _on(*, piano: Piano, staff: Staff) -> Score:
    """View the piano through the shared builders with inserts going to ``staff``."""
    return Score(document=piano.document, voice=piano.voice, staff=staff, measures=piano.measures)


def _notes(*, staff: Staff) -> list[int]:
    """List the staff steps of the notes on a staff, in order."""
    return sorted(item.staff_step for item in staff.musical_items if isinstance(item, Note))


@pytest.mark.unit
def test_a_same_span_note_on_the_other_staff_joins_the_chord() -> None:
    piano: Piano = build_piano()
    upper: Score = _on(piano=piano, staff=piano.upper)
    quarters(score=upper, measure=0)

    insert_note(
        score=_on(piano=piano, staff=piano.lower), at=_Q, rhythmic_value=RhythmicValue.QUARTER
    )

    assert layout(score=upper) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0,9"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert [
        (item.staff is piano.lower, item.staff_step)
        for item in note_at(score=upper, at=_Q).note_carrier.notes
    ] == [(False, 0), (True, NEW_STEP)]
    assert orphan_anchors(score=upper) == []


@pytest.mark.unit
def test_a_longer_note_replaces_a_chord_on_both_staffs() -> None:
    piano: Piano = build_piano()
    upper: Score = _on(piano=piano, staff=piano.upper)
    insert_note(score=upper, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, step=1)
    insert_note(
        score=_on(piano=piano, staff=piano.lower),
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=2,
    )
    assert layout(score=upper)[0] == slot(0, Fraction(0), _H, "1,2")

    insert_note(score=upper, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=upper) == [
        slot(0, Fraction(0), Fraction(3, 4), "9"),
        slot(0, Fraction(3, 4), _Q, "rest"),
    ]
    assert _notes(staff=piano.upper) == [NEW_STEP]
    assert _notes(staff=piano.lower) == []
    assert orphan_anchors(score=upper) == []
