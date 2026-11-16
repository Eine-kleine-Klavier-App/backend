from fractions import Fraction

import pytest
from tests.unit.domain.scene import Score, build_score, note_at, quarters

from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.steps import resolve_entities
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def _score() -> Score:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)

    return score


@pytest.mark.unit
def test_what_the_document_lists_is_found_by_its_id() -> None:
    score: Score = _score()
    voice, staff, measure = score.voice, score.staff, score.measures[1]

    found = resolve_entities(
        entities=EntityIndex(document=score.document), entity_ids=(voice.id, staff.id, measure.id)
    )

    assert found == {voice.id: voice, staff.id: staff, measure.id: measure}


@pytest.mark.unit
def test_an_entity_inside_the_score_is_found_by_its_id() -> None:
    score: Score = _score()
    carrier = note_at(score=score, at=Fraction(1, 4)).note_carrier

    found = resolve_entities(
        entities=EntityIndex(document=score.document), entity_ids=(carrier.id,)
    )

    assert found == {carrier.id: carrier}


@pytest.mark.unit
def test_listed_and_inner_entities_are_found_together() -> None:
    score: Score = _score()
    note = note_at(score=score, at=Fraction(0))

    found = resolve_entities(
        entities=EntityIndex(document=score.document),
        entity_ids=(score.measures[0].id, note.id, score.staff.id),
    )

    assert found == {
        score.measures[0].id: score.measures[0],
        note.id: note,
        score.staff.id: score.staff,
    }


@pytest.mark.unit
def test_an_id_the_score_does_not_hold_rejects_the_intent() -> None:
    score: Score = _score()

    with pytest.raises(MutationRejectedError, match="unknown"):
        resolve_entities(
            entities=EntityIndex(document=score.document), entity_ids=(score.voice.id, "unknown")
        )
