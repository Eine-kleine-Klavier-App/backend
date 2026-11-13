from fractions import Fraction

from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import InsertNoteIntent
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

from ...scene import (
    Score,
    apply_intent,
    build_score,
    layout,
    note,
    note_at,
    refresh_score,
    slot,
    value,
)

_Q: Fraction = Fraction(1, 4)


def _half_note_with_a_sharp(*, step: int) -> Score:
    """A measure holding one half note from its start, with a sharp."""
    score: Score = build_score(measure_count=1)
    leaf = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=step,
    )
    leaf.carrier.notes[0].set_accidental(accidental=Accidental.SHARP)

    return score


def _insert_quarter_on_the_second_beat(
    *, score: Score, step: int, accidental: Accidental | None
) -> MutationLog:
    """A quarter over the tail of the half note: the half note is replaced."""
    return apply_intent(
        score=score,
        intent=InsertNoteIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[0].id,
            position=MeasurePosition.of_fraction(fraction=_Q),
            written_value=value(RhythmicValue.QUARTER),
            staff_step=step,
            accidental=accidental,
        ),
    )


def test_a_note_inserted_over_the_tail_of_an_earlier_note_takes_its_sign_though_it_goes() -> None:
    """The sign is inferred from the notes before the new one as the score stands, before the
    gesture clears what the new note meets: the half note is replaced by a rest, and the new
    note still takes the sharp it carried."""
    score: Score = _half_note_with_a_sharp(step=1)

    log: MutationLog = _insert_quarter_on_the_second_beat(score=score, step=1, accidental=None)

    after: Score = refresh_score(score=score)
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _Q, "1"),
        slot(0, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]
    assert note_at(score=after, at=_Q).accidental is Accidental.SHARP

    log.rollback()
    restored: Score = refresh_score(score=score)
    assert note_at(score=restored, at=Fraction(0)).accidental is Accidental.SHARP


def test_a_sign_named_by_the_intent_wins_over_the_inferred_one() -> None:
    score: Score = _half_note_with_a_sharp(step=1)

    _insert_quarter_on_the_second_beat(score=score, step=1, accidental=Accidental.NATURAL)

    assert note_at(score=refresh_score(score=score), at=_Q).accidental is Accidental.NATURAL


def test_a_sign_on_another_step_does_not_reach_the_new_note() -> None:
    score: Score = _half_note_with_a_sharp(step=2)

    _insert_quarter_on_the_second_beat(score=score, step=1, accidental=None)

    assert note_at(score=refresh_score(score=score), at=_Q).accidental is Accidental.NATURAL
