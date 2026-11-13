from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    GroupSlot,
    Scene,
    Score,
    Slot,
    create_tuplet_with_note,
    delete_entities,
    group_layout,
    insert_note,
    layout,
    note_at,
    orphan_anchors,
    size,
    slot,
    tie_layout,
    triplet_scene,
    value,
)

# Behaviour at a tuplet's edges that the rework must keep. The scene: a quarter, an eighth
# triplet on beat two (staff steps 1, 2, 3), two quarters.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


def _triplet_of_rests() -> Score:
    """Build the triplet scene with the triplet's notes deleted one per gesture."""
    score: Score = triplet_scene()
    for index in range(3):
        delete_entities(score=score, entity_ids=[note_at(score=score, at=_Q + index * _THIRD).id])

    return score


def _triplet_slot() -> GroupSlot:
    return GroupSlot(
        measure_index=0,
        position=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        depth=0,
    )


@pytest.mark.unit
def test_a_nested_tuplet_is_created_with_its_first_note_in_one_triplet_slot() -> None:
    """Create three sixteenths in the time of the triplet's second eighth."""
    score: Score = triplet_scene()

    create_tuplet_with_note(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
        first=value(RhythmicValue.SIXTEENTH),
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _E, "1", depth=1),
        slot(0, _Q + _THIRD, Fraction(1, 16), "9", depth=2),
        slot(0, Fraction(13, 36), _E, "rest", depth=2),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == [
        _triplet_slot(),
        GroupSlot(
            measure_index=0,
            position=_Q + _THIRD,
            written=size(RhythmicValue.SIXTEENTH, count=3),
            occupied=size(RhythmicValue.EIGHTH),
            depth=1,
        ),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "scene",
    [
        pytest.param(triplet_scene, id="triplet of notes"),
        pytest.param(_triplet_of_rests, id="triplet of rests"),
    ],
)
def test_a_voice_level_note_over_a_tuplet_edge_removes_the_tuplet_whole(scene: Scene) -> None:
    """Remove the triplet as one element, whatever it holds.

    A dotted quarter from beat one meets the triplet at the voice's level; rests fill what
    the note leaves of its room.
    """
    score: Score = scene()
    assert group_layout(score=score) == [_triplet_slot()]

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(3, 8), "9"),
        slot(0, Fraction(3, 8), _E, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_note_running_past_its_tuplets_end_is_refused() -> None:
    score: Score = triplet_scene()
    before: list[Slot] = layout(score=score)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        insert_note(score=score, at=_Q + 2 * _THIRD, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == before
    assert group_layout(score=score) == [_triplet_slot()]


@pytest.mark.unit
def test_a_note_at_the_outer_triplets_level_removes_a_nested_tuplet_whole() -> None:
    """Remove the nested tuplet as one element of the outer triplet.

    A written quarter at the triplet's start covers its first eighth and the nested tuplet
    of three sixteenths in its second eighth.
    """
    score: Score = triplet_scene()
    create_tuplet_with_note(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
        first=value(RhythmicValue.SIXTEENTH),
        step=5,
    )

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "9", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == [_triplet_slot()]
    assert orphan_anchors(score=score) == []
