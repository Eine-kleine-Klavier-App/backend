from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import (
    MutationTransaction,
    build_compiler,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithNoteIntent,
    DeleteBatchIntent,
    EditIntent,
    InsertNoteIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    NEW_STEP,
    GroupSlot,
    Scene,
    Score,
    Slot,
    TieSlot,
    anchor_layout,
    apply_intent,
    apply_intents,
    build_engine,
    build_score,
    crossing_half,
    four_quarters,
    group_layout,
    layout,
    note_at,
    orphan_anchors,
    quarters,
    rest,
    rest_at,
    size,
    tie_layout,
    triplet_scene,
    value,
)

# A batch is one transaction over a sequence of intents: intent k is compiled against the
# document intent k-1 left and runs as its own pass (all axes, then the posts), so the
# batch leaves exactly what the same intents leave one gesture each — rests, groups, ties
# and anchors included — and it is one journal: one undo step.

_Q: Fraction = Fraction(1, 4)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline

type Step = Callable[[Score], EditIntent]
type Snapshot = tuple[list[Slot], list[GroupSlot], list[TieSlot], list[tuple[int, Fraction]]]


def _rests_between_notes() -> Score:
    """A quarter note, two quarter rests, a quarter note."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 3))
    for beat in (1, 2):
        rest(
            score=score,
            parent=score.voice,
            at=Fraction(beat, 4),
            rhythmic_value=RhythmicValue.QUARTER,
        )

    return score


def _snapshot(*, score: Score) -> Snapshot:
    return (
        layout(score=score),
        group_layout(score=score),
        tie_layout(score=score),
        anchor_layout(score=score),
    )


def _delete_note(at: Fraction) -> Step:
    return lambda score: DeleteBatchIntent(entity_ids=(note_at(score=score, at=at).id,))


def _delete_carrier(at: Fraction) -> Step:
    return lambda score: DeleteBatchIntent(
        entity_ids=(note_at(score=score, at=at).note_carrier.id,)
    )


def _delete_rest(at: Fraction) -> Step:
    return lambda score: DeleteBatchIntent(entity_ids=(rest_at(score=score, at=at).id,))


def _insert(at: Fraction, rhythmic_value: RhythmicValue) -> Step:
    return lambda score: InsertNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_value=value(rhythmic_value),
        staff_step=NEW_STEP,
        accidental=Accidental.NATURAL,
    )


def _triplet_with_note(at: Fraction) -> Step:
    return lambda score: CreateTupletWithNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_size=size(RhythmicValue.EIGHTH, count=3),
        occupied_size=size(RhythmicValue.QUARTER),
        written_value=value(RhythmicValue.EIGHTH),
        staff_step=NEW_STEP,
        accidental=Accidental.NATURAL,
    )


_SEQUENCES: list[object] = [
    pytest.param(
        four_quarters,
        [_delete_note(_Q), _delete_carrier(Fraction(1, 2))],
        id="two neighbouring quarters, one per intent",
    ),
    pytest.param(
        triplet_scene,
        [_delete_note(_Q), _delete_note(_Q + _THIRD), _delete_note(_Q + 2 * _THIRD)],
        id="every note of a triplet, one per intent",
    ),
    pytest.param(
        four_quarters,
        [_insert(Fraction(0), RhythmicValue.EIGHTH), _triplet_with_note(Fraction(1, 2))],
        id="an insert, then a new triplet",
    ),
    pytest.param(
        crossing_half,
        [_delete_carrier(Fraction(0)), _delete_rest(Fraction(5, 4))],
        id="a note, then a rest without a neighbour",
    ),
    pytest.param(
        _rests_between_notes,
        [_delete_rest(Fraction(1, 2)), _delete_carrier(Fraction(0))],
        id="a rest beside a rest, then a note",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("scene", "steps"), _SEQUENCES)
def test_a_batch_leaves_exactly_what_its_intents_leave_one_gesture_each(
    scene: Scene,
    steps: list[Step],
) -> None:
    batched: Score = scene()
    apply_intents(score=batched, intents=[step(batched) for step in steps])

    sequenced: Score = scene()
    for intent in [step(sequenced) for step in steps]:
        apply_intent(score=sequenced, intent=intent)

    assert _snapshot(score=batched) == _snapshot(score=sequenced)
    assert orphan_anchors(score=batched) == []


@pytest.mark.unit
@pytest.mark.parametrize(("scene", "steps"), _SEQUENCES)
def test_a_batch_is_one_journal_undone_and_redone_as_one_step(
    scene: Scene,
    steps: list[Step],
) -> None:
    score: Score = scene()
    before: Snapshot = _snapshot(score=score)

    log: MutationLog = apply_intents(score=score, intents=[step(score) for step in steps])
    after: Snapshot = _snapshot(score=score)
    log.rollback()

    assert _snapshot(score=score) == before

    log.reapply()

    assert _snapshot(score=score) == after


@pytest.mark.unit
def test_each_intent_is_compiled_against_what_the_one_before_left() -> None:
    """The second intent names a carrier the first one already deleted: it is refused when
    it is compiled, and the first intent is rolled back with it."""
    score: Score = four_quarters()
    before: Snapshot = _snapshot(score=score)
    intent: EditIntent = _delete_carrier(_Q)(score)

    with pytest.raises(MutationRejectedError, match="Could not resolve"):
        apply_intents(score=score, intents=[intent, intent])

    assert _snapshot(score=score) == before


@pytest.mark.unit
def test_an_intent_refused_by_the_engine_rolls_back_every_intent_before_it() -> None:
    score: Score = four_quarters()
    before: Snapshot = _snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="does not fit"):
        apply_intents(
            score=score,
            intents=[
                _delete_carrier(_Q)(score),
                _insert(Fraction(3, 4), RhythmicValue.WHOLE)(score),
            ],
        )

    assert _snapshot(score=score) == before


@pytest.mark.unit
def test_a_transaction_runs_passes_only_inside_its_block_and_is_entered_once() -> None:
    score: Score = four_quarters()
    transaction: MutationTransaction = build_engine().transaction(document=score.document)

    with pytest.raises(RuntimeError, match="inside its with block"):
        transaction.run(requests=[])

    with transaction:
        transaction.run(requests=[])

    with pytest.raises(RuntimeError, match="entered only once"), transaction:
        pass

    with pytest.raises(RuntimeError, match="inside its with block"):
        transaction.run(requests=[])


@pytest.mark.unit
def test_an_error_between_passes_rolls_back_the_passes_before_it() -> None:
    """Whatever escapes the block — not only an engine error — undoes the transaction."""
    score: Score = four_quarters()
    before: Snapshot = _snapshot(score=score)
    intent: EditIntent = _delete_carrier(_Q)(score)

    with (
        pytest.raises(LookupError, match="stop"),
        build_engine().transaction(document=score.document) as transaction,
    ):
        transaction.run(requests=build_compiler().compile(document=score.document, intent=intent))
        assert _snapshot(score=score) != before
        raise LookupError("stop")

    assert _snapshot(score=score) == before
