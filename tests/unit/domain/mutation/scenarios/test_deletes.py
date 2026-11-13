from collections.abc import Sequence
from fractions import Fraction
from typing import Literal

import pytest

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import RhythmicValue

from ...scene import (
    GroupSlot,
    Scene,
    Score,
    Shape,
    Slot,
    TieSlot,
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
    shape,
    size,
    slot,
    tie_layout,
    triplet_scene,
)

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline

type Form = Literal["notes", "reversed notes", "carriers", "mixed", "note and own carrier"]

_TRIPLET_NOTES: tuple[Fraction, ...] = (_Q, _Q + _THIRD, _Q + 2 * _THIRD)
_TWO_QUARTERS: tuple[Fraction, ...] = (_Q, Fraction(1, 2))
_TWO_TRIPLET_NOTES: tuple[Fraction, ...] = _TRIPLET_NOTES[:2]
_QUARTER_AND_TRIPLET_NOTE: tuple[Fraction, ...] = (Fraction(0), _Q)
_CROSSING_PIECES: tuple[Fraction, ...] = (Fraction(3, 4), Fraction(1))


def _triplet_slot() -> GroupSlot:
    return GroupSlot(
        measure_index=0,
        position=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        depth=0,
    )


# --- a piece of a long chain --------------------------------------------------------------


@pytest.mark.unit
def test_deleting_the_middle_piece_of_a_three_measure_note_removes_only_it_and_its_ties() -> None:
    """Remove the middle piece and both its ties, nothing else.

    A dotted whole from beat four is stored q~w~q over three measures; the emptied measure
    holds nothing afterwards.
    """
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    quarters(score=score, measure=2, beats=(1, 2, 3))
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.WHOLE, dots=1, step=1)
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(1, Fraction(0), 1), end=(2, Fraction(0), 1)),
    ]

    delete_entities(score=score, entity_ids=[note_at(score=score, at=Fraction(1)).id])

    slots: list[Slot] = layout(score=score)
    assert [entry for entry in slots if entry.measure_index == 0] == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1"),
    ]
    assert [entry for entry in slots if entry.measure_index == 1] == []
    assert [entry for entry in slots if entry.measure_index == 2] == [
        slot(2, Fraction(0), _Q, "1"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


# --- the same deletion expressed differently ----------------------------------------------


def _deleted(*, scene: Scene, positions: Sequence[Fraction], form: Form) -> Score:
    """Delete the notes at ``positions`` in one batch, naming them in the given form."""
    score: Score = scene()
    notes: list[Note] = [note_at(score=score, at=position) for position in positions]
    entity_ids: list[str] = []
    for index, item in enumerate(notes):
        if form in ("notes", "reversed notes") or (form == "mixed" and index % 2 == 0):
            entity_ids.append(item.id)
        elif form in ("carriers", "mixed"):
            entity_ids.append(item.note_carrier.id)
        else:
            entity_ids.extend([item.id, item.note_carrier.id])
    if form == "reversed notes":
        entity_ids.reverse()
    delete_entities(score=score, entity_ids=entity_ids)

    return score


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scene", "positions", "expected"),
    [
        pytest.param(
            four_quarters,
            _TWO_QUARTERS,
            Shape(
                groups=[],
                notes=[slot(0, Fraction(0), _Q, "0"), slot(0, Fraction(3, 4), _Q, "0")],
                ties=[],
                rests=[(_Q, Fraction(3, 4), 0)],
            ),
            id="two quarters",
        ),
        pytest.param(
            triplet_scene,
            _TWO_TRIPLET_NOTES,
            Shape(
                groups=[_triplet_slot()],
                notes=[
                    slot(0, Fraction(0), _Q, "0"),
                    slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
                    slot(0, Fraction(1, 2), _Q, "0"),
                    slot(0, Fraction(3, 4), _Q, "0"),
                ],
                ties=[],
                rests=[(_Q, _Q + 2 * _THIRD, 1)],
            ),
            id="two triplet notes",
        ),
        pytest.param(
            triplet_scene,
            _QUARTER_AND_TRIPLET_NOTE,
            Shape(
                groups=[_triplet_slot()],
                notes=[
                    slot(0, _Q + _THIRD, _E, "2", depth=1),
                    slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
                    slot(0, Fraction(1, 2), _Q, "0"),
                    slot(0, Fraction(3, 4), _Q, "0"),
                ],
                ties=[],
                rests=[(Fraction(0), _Q, 0), (_Q, _Q + _THIRD, 1)],
            ),
            id="quarter and triplet note",
        ),
        pytest.param(
            crossing_half,
            _CROSSING_PIECES,
            Shape(
                groups=[],
                notes=[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
                ties=[],
                rests=[(Fraction(3, 4), Fraction(2), 0)],
            ),
            id="crossing half",
        ),
    ],
)
def test_deleting_notes_leaves_the_expected_shape(
    scene: Scene,
    positions: tuple[Fraction, ...],
    expected: Shape,
) -> None:
    """Delete the notes by id in one batch; every triplet note is covered further below."""
    score: Score = _deleted(scene=scene, positions=positions, form="notes")

    assert shape(score=score) == expected
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scene", "positions", "form"),
    [
        pytest.param(four_quarters, _TWO_QUARTERS, "reversed notes", id="two quarters / reversed"),
        pytest.param(four_quarters, _TWO_QUARTERS, "carriers", id="two quarters / carriers"),
        pytest.param(four_quarters, _TWO_QUARTERS, "mixed", id="two quarters / mixed"),
        pytest.param(
            four_quarters, _TWO_QUARTERS, "note and own carrier", id="two quarters / both"
        ),
        pytest.param(
            triplet_scene, _TRIPLET_NOTES, "reversed notes", id="whole triplet / reversed"
        ),
        pytest.param(triplet_scene, _TRIPLET_NOTES, "carriers", id="whole triplet / carriers"),
        pytest.param(triplet_scene, _TRIPLET_NOTES, "mixed", id="whole triplet / mixed"),
        pytest.param(
            triplet_scene, _TRIPLET_NOTES, "note and own carrier", id="whole triplet / both"
        ),
        pytest.param(
            triplet_scene,
            _TWO_TRIPLET_NOTES,
            "reversed notes",
            id="two triplet notes / reversed",
        ),
        pytest.param(
            triplet_scene, _TWO_TRIPLET_NOTES, "carriers", id="two triplet notes / carriers"
        ),
        pytest.param(
            triplet_scene,
            _TWO_TRIPLET_NOTES,
            "mixed",
            id="two triplet notes / mixed",
        ),
        pytest.param(
            triplet_scene, _TWO_TRIPLET_NOTES, "note and own carrier", id="two triplet notes / both"
        ),
        pytest.param(
            triplet_scene,
            _QUARTER_AND_TRIPLET_NOTE,
            "reversed notes",
            id="quarter and triplet note / reversed",
        ),
        pytest.param(
            triplet_scene,
            _QUARTER_AND_TRIPLET_NOTE,
            "carriers",
            id="quarter and triplet note / carriers",
        ),
        pytest.param(
            triplet_scene, _QUARTER_AND_TRIPLET_NOTE, "mixed", id="quarter and triplet note / mixed"
        ),
        pytest.param(
            triplet_scene,
            _QUARTER_AND_TRIPLET_NOTE,
            "note and own carrier",
            id="quarter and triplet note / both",
        ),
        pytest.param(
            crossing_half, _CROSSING_PIECES, "reversed notes", id="crossing half / reversed"
        ),
        pytest.param(crossing_half, _CROSSING_PIECES, "carriers", id="crossing half / carriers"),
        pytest.param(crossing_half, _CROSSING_PIECES, "mixed", id="crossing half / mixed"),
        pytest.param(
            crossing_half, _CROSSING_PIECES, "note and own carrier", id="crossing half / both"
        ),
    ],
)
def test_a_deletion_leaves_the_same_score_however_its_entities_are_named(
    scene: Scene,
    positions: tuple[Fraction, ...],
    form: Form,
) -> None:
    """Leave one result for one deletion in one gesture, rests included."""
    by_notes: Score = _deleted(scene=scene, positions=positions, form="notes")
    other: Score = _deleted(scene=scene, positions=positions, form=form)

    assert layout(score=other) == layout(score=by_notes)
    assert tie_layout(score=other) == tie_layout(score=by_notes)
    assert group_layout(score=other) == group_layout(score=by_notes)
    assert orphan_anchors(score=other) == []


# --- every note of a triplet --------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "gestures",
    [
        pytest.param([[0, 1, 2]], id="one batch"),
        pytest.param([[0], [1], [2]], id="one per gesture"),
        pytest.param([[0, 1], [2]], id="two then one"),
    ],
)
def test_deleting_every_note_of_a_triplet_keeps_the_triplet_on_every_path(
    gestures: list[list[int]],
) -> None:
    """Keep the triplet and tile it with rests, whichever way its notes were deleted.

    The voice has other notes in the triplet's measure, so an emptied triplet stays.
    """
    score: Score = triplet_scene()
    note_ids: list[str] = [note_at(score=score, at=position).id for position in _TRIPLET_NOTES]

    for gesture in gestures:
        delete_entities(score=score, entity_ids=[note_ids[index] for index in gesture])

    assert shape(score=score) == Shape(
        groups=[_triplet_slot()],
        notes=[
            slot(0, Fraction(0), _Q, "0"),
            slot(0, Fraction(1, 2), _Q, "0"),
            slot(0, Fraction(3, 4), _Q, "0"),
        ],
        ties=[],
        rests=[(_Q, Fraction(1, 2), 1)],
    )
    assert orphan_anchors(score=score) == []
