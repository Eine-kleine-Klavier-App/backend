from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, Ornament, RhythmicValue
from piano_app.domain.score.document.services.mutation.compiler import (
    CarrierMarks,
    SetCarrierMarksIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    Score,
    Snapshot,
    apply_intent,
    build_score,
    four_quarters,
    note_at,
    quarters,
    rest,
    rest_at,
    snapshot,
)

# SetCarrierMarks: the marks of several note carriers in ONE gesture, so one undo takes them
# all back. A mark left as None is not touched.


def carrier(*, score: Score, beat: int) -> NoteCarrier:
    return note_at(score=score, at=Fraction(beat, 4)).note_carrier


def marks(
    carrier: NoteCarrier,
    *,
    articulations: set[Articulation] | None = None,
    ornament: Ornament | None = None,
) -> CarrierMarks:
    return CarrierMarks(
        carrier_id=carrier.id,
        articulations=None if articulations is None else frozenset(articulations),
        ornament=ornament,
    )


@pytest.mark.unit
def test_one_batch_marks_every_named_carrier_and_leaves_the_others() -> None:
    score: Score = four_quarters()
    first, second, third = (carrier(score=score, beat=beat) for beat in (0, 1, 3))
    untouched: NoteCarrier = carrier(score=score, beat=2)
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=SetCarrierMarksIntent(
            items=(
                marks(first, ornament=Ornament.TRILL),
                marks(second, ornament=Ornament.TRILL),
                marks(third, ornament=Ornament.TRILL, articulations={Articulation.STACCATO}),
            )
        ),
    )

    assert snapshot(score=score) == before
    assert [c.ornament for c in (first, second, third, untouched)] == [
        Ornament.TRILL,
        Ornament.TRILL,
        Ornament.TRILL,
        Ornament.NONE,
    ]
    assert third.articulations == {Articulation.STACCATO}
    assert untouched.articulations == set()


@pytest.mark.unit
def test_a_mark_left_out_is_not_touched() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = carrier(score=score, beat=1)
    apply_intent(
        score=score,
        intent=SetCarrierMarksIntent(
            items=(marks(target, ornament=Ornament.TURN, articulations={Articulation.ACCENT}),)
        ),
    )

    apply_intent(
        score=score,
        intent=SetCarrierMarksIntent(items=(marks(target, articulations=set()),)),
    )

    assert (target.ornament, target.articulations) == (Ornament.TURN, set())


@pytest.mark.unit
def test_one_undo_takes_the_whole_batch_back_and_redo_sets_it_again() -> None:
    score: Score = four_quarters()
    targets: list[NoteCarrier] = [carrier(score=score, beat=beat) for beat in range(3)]
    before: Snapshot = snapshot(score=score)

    log: MutationLog = apply_intent(
        score=score,
        intent=SetCarrierMarksIntent(
            items=tuple(
                marks(target, ornament=Ornament.LOWER_MORDENT, articulations={Articulation.TENUTO})
                for target in targets
            )
        ),
    )
    log.rollback()

    assert snapshot(score=score) == before
    assert [(t.ornament, t.articulations) for t in targets] == [(Ornament.NONE, set())] * 3

    log.reapply()
    assert all(
        (t.ornament, t.articulations) == (Ornament.LOWER_MORDENT, {Articulation.TENUTO})
        for t in targets
    )


@pytest.mark.unit
def test_a_refused_item_changes_nothing_of_the_batch() -> None:
    """A set with two marks of one category is refused; the carriers before it stay as they were."""
    score: Score = four_quarters()
    good, bad = carrier(score=score, beat=0), carrier(score=score, beat=1)
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError):
        apply_intent(
            score=score,
            intent=SetCarrierMarksIntent(
                items=(
                    marks(good, ornament=Ornament.TRILL),
                    marks(bad, articulations={Articulation.STACCATO, Articulation.TENUTO}),
                )
            ),
        )

    assert snapshot(score=score) == before
    assert good.ornament is Ornament.NONE


@pytest.mark.unit
def test_a_rest_carrier_an_unknown_id_a_repeat_an_empty_batch_and_an_empty_item_are_refused() -> (
    None
):
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    target: NoteCarrier = carrier(score=score, beat=1)
    before: Snapshot = snapshot(score=score)

    refused: list[tuple[SetCarrierMarksIntent, str]] = [
        (
            SetCarrierMarksIntent(
                items=(
                    CarrierMarks(
                        carrier_id=rest_at(score=score, at=Fraction(0)).rest_carrier.id,
                        ornament=Ornament.TRILL,
                    ),
                )
            ),
            "NoteCarrier",
        ),
        (
            SetCarrierMarksIntent(
                items=(CarrierMarks(carrier_id="nope", ornament=Ornament.TRILL),)
            ),
            "not resolve",
        ),
        (
            SetCarrierMarksIntent(
                items=(
                    marks(target, ornament=Ornament.TRILL),
                    marks(target, ornament=Ornament.TURN),
                )
            ),
            "once",
        ),
        (SetCarrierMarksIntent(items=()), "at least one"),
        (SetCarrierMarksIntent(items=(marks(target),)), "sets something"),
    ]
    for intent, message in refused:
        with pytest.raises(MutationRejectedError, match=message):
            apply_intent(score=score, intent=intent)

    assert snapshot(score=score) == before
