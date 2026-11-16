from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    EditIntent,
    InsertNoteIntent,
)

from ..scene import (
    NEW_STEP,
    Score,
    build_engine,
    build_score,
    contained_ids,
    note_at,
    quarters,
    value,
)

# The index of a document's entities answers by id, and goes on answering right as the
# transactions it is handed to change the document, without being built again.


def _score() -> Score:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)

    return score


def _run(*, score: Score, entities: EntityIndex, intent: EditIntent) -> None:
    """One intent compiled against the index and run in a transaction that keeps the index."""
    with build_engine().transaction(document=score.document, entities=entities) as transaction:
        transaction.run(
            requests=build_compiler().compile(
                document=score.document, intent=intent, entities=entities
            )
        )


def _insert_quarter(*, score: Score, entities: EntityIndex, at: Fraction) -> None:
    _run(
        score=score,
        entities=entities,
        intent=InsertNoteIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[int(at)].id,
            position=MeasurePosition.of_fraction(fraction=at - int(at)),
            written_value=value(RhythmicValue.QUARTER),
            staff_step=NEW_STEP,
            accidental=Accidental.NATURAL,
            beam_share=Fraction(1),
        ),
    )


def _parts_of(*, note: Note) -> list[ScoreEntity]:
    """The note, its carrier and the leaf that holds the carrier."""
    carrier: NoteCarrier = note.note_carrier
    leaf: object = carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)

    return [note, carrier, leaf, leaf.anchor]


@pytest.mark.unit
def test_every_kind_of_entity_the_document_holds_is_found_by_its_id() -> None:
    score: Score = _score()
    entities: EntityIndex = EntityIndex(document=score.document)
    note: Note = note_at(score=score, at=Fraction(1, 4))

    for entity in (score.voice, score.staff, score.measures[1], *_parts_of(note=note)):
        assert entities.find(entity_id=entity.id) is entity


@pytest.mark.unit
def test_an_id_the_document_does_not_hold_is_found_nowhere() -> None:
    score: Score = _score()

    assert EntityIndex(document=score.document).find(entity_id="ghost") is None


@pytest.mark.unit
def test_a_note_inserted_in_a_transaction_that_keeps_the_index_is_found_afterwards() -> None:
    score: Score = _score()
    entities: EntityIndex = EntityIndex(document=score.document)
    assert entities.held().keys() == contained_ids(document=score.document)

    _insert_quarter(score=score, entities=entities, at=Fraction(1))
    inserted: Note = note_at(score=score, at=Fraction(1))

    for entity in _parts_of(note=inserted):
        assert entities.find(entity_id=entity.id) is entity
    assert entities.held().keys() == contained_ids(document=score.document)


@pytest.mark.unit
def test_a_note_deleted_takes_its_carrier_and_leaf_out_and_leaves_the_rest() -> None:
    score: Score = _score()
    entities: EntityIndex = EntityIndex(document=score.document)
    gone: Note = note_at(score=score, at=Fraction(1, 4))
    kept: Note = note_at(score=score, at=Fraction(1, 2))
    parts: list[ScoreEntity] = _parts_of(note=gone)

    _run(score=score, entities=entities, intent=DeleteBatchIntent(entity_ids=(gone.id,)))

    assert entities.find(entity_id=gone.id) is None
    assert entities.find(entity_id=gone.note_carrier.id) is None
    assert entities.find(entity_id=kept.id) is kept
    assert all(entities.find(entity_id=entity.id) is None for entity in parts[:3])
    assert entities.held().keys() == contained_ids(document=score.document)


@pytest.mark.unit
def test_an_index_kept_through_several_edits_agrees_with_one_built_afterwards() -> None:
    score: Score = _score()
    entities: EntityIndex = EntityIndex(document=score.document)
    assert entities.held()

    _insert_quarter(score=score, entities=entities, at=Fraction(1))
    _insert_quarter(score=score, entities=entities, at=Fraction(5, 4))
    _run(
        score=score,
        entities=entities,
        intent=DeleteBatchIntent(entity_ids=(note_at(score=score, at=Fraction(0)).id,)),
    )

    rebuilt: EntityIndex = EntityIndex(document=score.document)

    assert entities.held().keys() == rebuilt.held().keys()
    assert all(rebuilt.held()[key] is entity for key, entity in entities.held().items())


@pytest.mark.unit
def test_an_index_never_read_before_the_edits_is_built_from_the_document_as_it_is() -> None:
    score: Score = _score()
    entities: EntityIndex = EntityIndex(document=score.document)

    _insert_quarter(score=score, entities=entities, at=Fraction(1))

    assert entities.held().keys() == contained_ids(document=score.document)
