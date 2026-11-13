from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    Ornament,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation.compiler import TieNotesIntent
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    Score,
    apply_intent,
    build_score,
    four_quarters,
    insert_note,
    note,
    note_at,
    quarters,
)

# A tie is a relation of notes; the articulations and the ornament are marks of a carrier. They
# are independent, except that a tie which leaves the second carrier with no new note of its own
# overwrites that carrier's marks with the first one's, at the moment the tie is made.

_Q: Fraction = Fraction(1, 4)


def _tie(*, score: Score, start: Note, end: Note) -> None:
    apply_intent(score=score, intent=TieNotesIntent(start_note_id=start.id, end_note_id=end.id))


def _mark(*, carrier: NoteCarrier, articulations: set[Articulation], ornament: Ornament) -> None:
    carrier.set_articulations(articulations=frozenset(articulations))
    carrier.set_ornament(ornament=ornament)


def _a_quarter_and_a_higher_quarter() -> Score:
    """Beat one and beat two sound different, so they cannot be tied."""
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    note(
        score=score,
        parent=score.voice,
        at=_Q,
        rhythmic_value=RhythmicValue.QUARTER,
        step=3,
    )
    quarters(score=score, measure=0, beats=(2, 3))

    return score


@pytest.mark.unit
def test_a_tie_overwrites_the_marks_of_a_carrier_that_only_continues() -> None:
    score: Score = four_quarters()
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    _mark(
        carrier=start.note_carrier,
        articulations={Articulation.STACCATO, Articulation.ACCENT},
        ornament=Ornament.TRILL,
    )
    _mark(carrier=end.note_carrier, articulations={Articulation.TENUTO}, ornament=Ornament.TURN)

    _tie(score=score, start=start, end=end)

    assert end.note_carrier.articulations == {Articulation.STACCATO, Articulation.ACCENT}
    assert end.note_carrier.ornament is Ornament.TRILL


@pytest.mark.unit
def test_a_tie_between_carriers_with_equal_marks_changes_nothing_else() -> None:
    score: Score = four_quarters()
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    for carrier in (start.note_carrier, end.note_carrier):
        _mark(carrier=carrier, articulations={Articulation.MARCATO}, ornament=Ornament.TURN)

    _tie(score=score, start=start, end=end)

    assert end.note_carrier.articulations == {Articulation.MARCATO}
    assert end.note_carrier.ornament is Ornament.TURN
    assert start.note_carrier.articulations == {Articulation.MARCATO}


@pytest.mark.unit
def test_a_tie_of_one_note_of_a_chord_leaves_the_marks_of_the_second_carrier() -> None:
    """Both quarters are chords; only the lower notes are tied, so the second carrier has a
    new note of its own and keeps its marks."""
    score: Score = four_quarters()
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    assert len(start.note_carrier.notes) == len(end.note_carrier.notes) == 2
    _mark(
        carrier=start.note_carrier,
        articulations={Articulation.STACCATO},
        ornament=Ornament.TRILL,
    )
    _mark(carrier=end.note_carrier, articulations={Articulation.ACCENT}, ornament=Ornament.TURN)

    _tie(score=score, start=start, end=end)

    assert end.note_carrier.articulations == {Articulation.ACCENT}
    assert end.note_carrier.ornament is Ornament.TURN


@pytest.mark.unit
def test_a_tie_that_completes_a_chord_of_continuations_overwrites_its_marks() -> None:
    """Both notes of the second chord end a tie once the second tie exists, so the carrier
    only continues and takes the first carrier's marks."""
    score: Score = four_quarters()
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    first_start, second_start = note_at(score=score, at=Fraction(0)).note_carrier.notes
    first_end, second_end = note_at(score=score, at=_Q).note_carrier.notes
    _mark(
        carrier=first_start.note_carrier,
        articulations={Articulation.TENUTO},
        ornament=Ornament.UPPER_MORDENT,
    )
    _mark(
        carrier=first_end.note_carrier,
        articulations={Articulation.ACCENT},
        ornament=Ornament.NONE,
    )

    _tie(score=score, start=first_start, end=first_end)

    assert first_end.note_carrier.articulations == {Articulation.ACCENT}

    _tie(score=score, start=second_start, end=second_end)

    assert second_end.note_carrier.articulations == {Articulation.TENUTO}
    assert second_end.note_carrier.ornament is Ornament.UPPER_MORDENT


@pytest.mark.unit
def test_a_refused_tie_leaves_the_marks_as_they_were() -> None:
    """The second note sounds different, so the tie is refused and the overwrite goes with it."""
    score: Score = _a_quarter_and_a_higher_quarter()
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    _mark(
        carrier=start.note_carrier, articulations={Articulation.STACCATO}, ornament=Ornament.TRILL
    )
    _mark(carrier=end.note_carrier, articulations={Articulation.ACCENT}, ornament=Ornament.TURN)

    with pytest.raises(MutationRejectedError, match="must sound the same"):
        _tie(score=score, start=start, end=end)

    assert end.note_carrier.articulations == {Articulation.ACCENT}
    assert end.note_carrier.ornament is Ornament.TURN
