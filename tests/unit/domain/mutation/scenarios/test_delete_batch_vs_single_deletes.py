from fractions import Fraction

import pytest

from ...scene import (
    Scene,
    Score,
    crossing_half,
    crossing_triplet,
    delete_entities,
    four_quarters,
    note_at,
    orphan_anchors,
    shape,
    triplet_scene,
)

# Deleting a set of notes in one DeleteBatch leaves the same groups, notes and ties as
# deleting them one per gesture. Rests are compared by the time they cover at each depth
# only — how rests are spelled across separate gestures is an open owner question. A
# triplet emptied beside other notes stays on both paths. (The batch == sequence property
# of one transaction over several intents is in test_transaction.py.)

_Q: Fraction = Fraction(1, 4)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scene", "positions"),
    [
        pytest.param(four_quarters, (_Q, Fraction(1, 2)), id="two adjacent quarters"),
        pytest.param(four_quarters, (Fraction(0), Fraction(3, 4)), id="first and last quarter"),
        pytest.param(four_quarters, (Fraction(0), _Q, Fraction(1, 2)), id="three quarters"),
        pytest.param(
            crossing_half, (Fraction(3, 4), Fraction(1)), id="both pieces of a crossing half"
        ),
        pytest.param(crossing_half, (Fraction(1),), id="the tail of a crossing half"),
        pytest.param(triplet_scene, (_Q, _Q + 2 * _THIRD), id="outer notes of a triplet"),
        pytest.param(triplet_scene, (Fraction(0), _Q), id="a quarter and a triplet's first"),
        pytest.param(
            triplet_scene,
            (_Q, _Q + _THIRD, _Q + 2 * _THIRD),
            id="all notes of a triplet",
        ),
        pytest.param(
            crossing_triplet,
            (Fraction(11, 12), Fraction(1)),
            id="both pieces of a tied note in a crossing triplet",
        ),
        pytest.param(
            crossing_triplet,
            (Fraction(3, 4), Fraction(11, 12), Fraction(1), Fraction(13, 12)),
            id="all notes of a crossing triplet",
        ),
    ],
)
def test_a_batch_delete_leaves_what_one_delete_per_gesture_leaves(
    scene: Scene,
    positions: tuple[Fraction, ...],
) -> None:
    batched: Score = scene()
    delete_entities(
        score=batched,
        entity_ids=[note_at(score=batched, at=position).id for position in positions],
    )

    sequenced: Score = scene()
    note_ids: list[str] = [note_at(score=sequenced, at=position).id for position in positions]
    for note_id in note_ids:
        delete_entities(score=sequenced, entity_ids=[note_id])

    assert shape(score=batched) == shape(score=sequenced)
    assert orphan_anchors(score=batched) == []
    assert orphan_anchors(score=sequenced) == []
