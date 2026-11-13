from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent

from ...scene import (
    NEW_STEP,
    Score,
    apply_intent,
    delete_entities,
    four_quarters,
    note_at,
    value,
)

# Grace notes in a delete batch: the remove analyzer decides on the live document what each
# named grace note, item or group comes to.


def _first_leaf(score: Score) -> LeafRhythmicContainer:
    return iter_leaves(score.voice)[0]


def _add(score: Score, placement: GracePlacement) -> None:
    apply_intent(
        score=score,
        intent=AddGraceNoteIntent(
            host_carrier_id=note_at(score=score, at=Fraction(0)).note_carrier.id,
            placement=placement,
            grace_type=GraceType.APPOGGIATURA,
            written_value=value(RhythmicValue.SIXTEENTH),
            staff_id=score.staff.id,
            staff_step=NEW_STEP,
            accidental=Accidental.NATURAL,
        ),
    )


def _notes(group: GraceGroup | None) -> list[Note]:
    assert group is not None
    return [
        note
        for item in group.grace_items
        if isinstance(item.carrier, NoteCarrier)
        for note in item.carrier.notes
    ]


@pytest.mark.unit
def test_naming_one_grace_note_of_two_removes_it_and_keeps_the_group() -> None:
    score: Score = four_quarters()
    _add(score, GracePlacement.BEFORE)
    _add(score, GracePlacement.BEFORE)
    leaf = _first_leaf(score)
    group = leaf.grace_before
    first, second = _notes(group)

    delete_entities(score=score, entity_ids=[first.id])

    assert leaf.grace_before is group
    assert _notes(group) == [second]


@pytest.mark.unit
def test_naming_every_grace_note_of_a_group_removes_the_group() -> None:
    score: Score = four_quarters()
    _add(score, GracePlacement.BEFORE)
    _add(score, GracePlacement.BEFORE)
    leaf = _first_leaf(score)

    delete_entities(score=score, entity_ids=[note.id for note in _notes(leaf.grace_before)])

    assert leaf.grace_before is None


@pytest.mark.unit
def test_naming_a_group_and_its_note_together_is_the_same_as_naming_the_group() -> None:
    score: Score = four_quarters()
    _add(score, GracePlacement.AFTER)
    leaf = _first_leaf(score)
    group = leaf.grace_after
    assert group is not None

    delete_entities(score=score, entity_ids=[group.id, _notes(group)[0].id])

    assert leaf.grace_after is None


@pytest.mark.unit
def test_naming_grace_notes_of_both_sides_removes_both_groups_and_an_undo_brings_them_back() -> (
    None
):
    score: Score = four_quarters()
    _add(score, GracePlacement.BEFORE)
    _add(score, GracePlacement.AFTER)
    leaf = _first_leaf(score)
    named = [*_notes(leaf.grace_before), *_notes(leaf.grace_after)]

    log = delete_entities(score=score, entity_ids=[note.id for note in named])
    assert leaf.grace_before is None
    assert leaf.grace_after is None

    log.rollback()
    assert len(_notes(leaf.grace_before)) == 1
    assert len(_notes(leaf.grace_after)) == 1


@pytest.mark.unit
def test_naming_a_note_and_its_grace_notes_together_removes_everything() -> None:
    """The host's leaf takes its groups with it, so the grace notes named beside it are no
    error and nothing of them is left."""
    score: Score = four_quarters()
    _add(score, GracePlacement.BEFORE)
    _add(score, GracePlacement.AFTER)
    leaf = _first_leaf(score)
    grace_ids = [note.id for note in (*_notes(leaf.grace_before), *_notes(leaf.grace_after))]

    delete_entities(score=score, entity_ids=[leaf.id, *grace_ids])

    assert leaf.grace_before is None
    assert leaf.grace_after is None
