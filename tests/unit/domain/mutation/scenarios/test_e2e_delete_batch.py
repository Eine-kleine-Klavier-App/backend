from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import (
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import GraceGroup, GraceItem
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.compiler import TieNotesIntent
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    NEW_STEP,
    Score,
    Slot,
    Snapshot,
    anchor_layout,
    apply_intent,
    build_score,
    crossing_half,
    delete_entities,
    four_quarters,
    group_layout,
    insert_note,
    layout,
    note_at,
    orphan_anchors,
    quarters,
    slot,
    snapshot,
    tie_layout,
    triplet_scene,
    value,
)

# A delete batch end to end: the compiler only addresses, the remove request orders the
# listed entities and every cascade is its entity's own analyzer, then the posts.

_Q: Fraction = Fraction(1, 4)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


@pytest.mark.unit
def test_deleting_a_group_drops_the_tie_its_note_had_to_a_note_outside() -> None:
    """The triplet's last eighth is tied to the quarter after the triplet. The triplet goes
    with its notes and their ties; the quarter outside stays, untied."""
    score: Score = triplet_scene()
    outside: Note = note_at(score=score, at=Fraction(1, 2))
    # a tie joins notes of one pitch
    note_at(score=score, at=_Q + 2 * _THIRD).set_staff_step(staff_step=0)
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=_Q + 2 * _THIRD).id,
            end_note_id=outside.id,
        ),
    )
    triplet = score.voice.children[1]

    delete_entities(score=score, entity_ids=[triplet.id])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert note_at(score=score, at=Fraction(1, 2)) is outside
    assert list(outside.relations) == []
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


def _a_tie() -> tuple[Score, ScoreEntity]:
    score: Score = crossing_half()

    return score, note_at(score=score, at=Fraction(3, 4)).relations[0]


@pytest.mark.unit
def test_a_delete_batch_naming_a_tie_removes_it_with_the_note_beside_it() -> None:
    """A relation goes like any other entity: the note listed beside it goes too and its hole
    is filled; the scene's other leaves stay, and so do the contexts every score starts with."""
    score, removed = _a_tie()
    leaves: list[Slot] = layout(score=score)

    delete_entities(
        score=score,
        entity_ids=[note_at(score=score, at=Fraction(0)).id, removed.id],
    )

    assert layout(score=score) == [slot(0, Fraction(0), _Q, "rest"), *leaves[1:]]
    assert tie_layout(score=score) == []
    assert score.document.missing_initial_contexts() == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "refused_id"),
    [
        pytest.param("Voice", lambda score: score.voice.id, id="a voice"),
        pytest.param("Staff", lambda score: score.staff.id, id="a staff"),
    ],
)
def test_a_delete_batch_naming_a_voice_or_a_staff_is_refused_and_changes_nothing(
    kind: str,
    refused_id: Callable[[Score], str],
) -> None:
    """Voices and staffs are not deleted by this intent: the compiler refuses the whole
    batch, the note listed beside it included."""
    score: Score = crossing_half()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match=f"Unsupported delete targets: {kind}"):
        delete_entities(
            score=score,
            entity_ids=[note_at(score=score, at=Fraction(0)).id, refused_id(score)],
        )

    assert snapshot(score=score) == before


def _grace_entities(*, score: Score) -> dict[str, ScoreEntity]:
    """A grace note and a grace rest before the first quarter, each entity by its kind."""
    group: GraceGroup = GraceGroup.create(
        leaf=iter_leaves(score.voice)[0],
        grace_type=GraceType.ACCIACCATURA,
        placement=GracePlacement.BEFORE,
    )
    note_item: GraceItem = GraceItem.create(
        grace_group=group,
        rhythmic_value=value(RhythmicValue.EIGHTH),
    )
    note_carrier: NoteCarrier = NoteCarrier.create(owner=note_item)
    grace_note: Note = Note.create(
        note_carrier=note_carrier,
        staff=score.staff,
        staff_step=NEW_STEP,
        accidental=Accidental.NATURAL,
    )
    rest_item: GraceItem = GraceItem.create(
        grace_group=group,
        rhythmic_value=value(RhythmicValue.EIGHTH),
    )
    rest_carrier: RestCarrier = RestCarrier.create(owner=rest_item)
    grace_rest: Rest = Rest.create(rest_carrier=rest_carrier, staff=score.staff)

    return {
        "GraceGroup": group,
        "GraceItem": note_item,
        "NoteCarrier": note_carrier,
        "Note": grace_note,
        "RestCarrier": rest_carrier,
        "Rest": grace_rest,
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "items_left"),
    [
        ("GraceGroup", None),
        ("GraceItem", 1),
        ("NoteCarrier", 1),
        ("Note", 1),
        ("RestCarrier", 1),
        ("Rest", 1),
    ],
)
def test_a_delete_batch_naming_a_grace_element_removes_that_element(
    kind: str, items_left: int | None
) -> None:
    """Naming the group removes it whole; naming a carrier, note or rest of one of its two
    items removes that item and leaves the other."""
    score: Score = four_quarters()
    named: ScoreEntity = _grace_entities(score=score)[kind]
    leaf = iter_leaves(score.voice)[0]
    group: GraceGroup | None = leaf.grace_before
    assert group is not None

    delete_entities(score=score, entity_ids=[named.id])

    if items_left is None:
        assert leaf.grace_before is None
    else:
        assert leaf.grace_before is group
        assert len(group.grace_items) == items_left


@pytest.mark.unit
def test_a_batch_naming_one_note_of_a_chord_keeps_the_chord_carrier() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    kept, gone = carrier.notes
    assert gone.staff_step == NEW_STEP
    leaves, groups, ties, anchors = snapshot(score=score)

    delete_entities(score=score, entity_ids=[gone.id])

    assert snapshot(score=score) == (
        [slot(0, Fraction(0), _Q, "0"), *leaves[1:]],
        groups,
        ties,
        anchors,
    )
    assert note_at(score=score, at=Fraction(0)).note_carrier is carrier
    assert list(carrier.notes) == [kept]
    assert gone not in score.staff.musical_items
