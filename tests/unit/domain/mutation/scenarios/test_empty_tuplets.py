from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.helpers import iter_leaves

from ...scene import (
    GroupSlot,
    Score,
    Shape,
    anchor_layout,
    anchor_positions,
    build_engine,
    build_score,
    delete_entities,
    eighth_triplet,
    group,
    group_layout,
    layout,
    note,
    orphan_anchors,
    quarters,
    shape,
    size,
    slot,
)

# The posts run once per intent, in order: leaves without content, then empty groups,
# then the fill, then orphan anchors. An empty tuplet goes only where its voice holds
# nothing else in the measures it reaches; with other content of the voice around it
# stays and is tiled. A tuplet of rests is content and stays.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


def _note_ids(*, parent: GroupRhythmicContainer) -> list[str]:
    """Every note held anywhere inside ``parent``, outer leaves and nested ones alike."""
    ids: list[str] = []
    for leaf in iter_leaves(parent):
        carrier: Carrier | None = leaf.carrier
        if isinstance(carrier, NoteCarrier):
            ids.extend(item.id for item in carrier.notes)

    return ids


def _assert_settled(*, score: Score) -> None:
    """No orphan anchor is left, and running the posts again changes nothing."""
    before: tuple[object, ...] = (
        layout(score=score),
        group_layout(score=score),
        anchor_layout(score=score),
    )

    build_engine().process(document=score.document, requests=[])

    assert orphan_anchors(score=score) == []
    assert (layout(score=score), group_layout(score=score), anchor_layout(score=score)) == before


def _triplet_alone() -> tuple[Score, GroupRhythmicContainer]:
    """An eighth triplet on beat two of a measure the voice holds nothing else in."""
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)

    return score, triplet


def _triplet_beside_notes() -> tuple[Score, GroupRhythmicContainer]:
    """A quarter, an eighth triplet on beat two, two quarters."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))

    return score, triplet


def _triplet_slot() -> GroupSlot:
    return GroupSlot(
        measure_index=0,
        position=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        depth=0,
    )


# --- one tuplet ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_tuplet_emptied_in_one_batch_in_an_otherwise_empty_measure_is_removed() -> None:
    """Nothing else of the voice is in the measure: the tuplet goes, and the measure,
    holding nothing, is left asleep."""
    score, triplet = _triplet_alone()

    delete_entities(score=score, entity_ids=_note_ids(parent=triplet))

    assert score.voice.children == []
    assert anchor_positions(score.measures[0]) == [Fraction(0)]
    _assert_settled(score=score)


@pytest.mark.unit
def test_a_tuplet_emptied_one_by_one_in_an_otherwise_empty_measure_keeps_its_rests() -> None:
    """Every gesture refills the hole it makes, so the tuplet is never empty: a tuplet of
    rests is content and stays (the accepted difference from the one-batch path)."""
    score, triplet = _triplet_alone()

    for note_id in _note_ids(parent=triplet):
        delete_entities(score=score, entity_ids=[note_id])

    assert triplet in score.voice.children
    assert shape(score=score) == Shape(
        groups=[_triplet_slot()],
        notes=[],
        ties=[],
        rests=[(Fraction(0), _Q, 0), (_Q, Fraction(1, 2), 1), (Fraction(1, 2), Fraction(1), 0)],
    )
    _assert_settled(score=score)


@pytest.mark.unit
@pytest.mark.parametrize("one_by_one", [False, True], ids=["one batch", "one by one"])
def test_a_tuplet_emptied_beside_other_notes_stays_and_is_tiled(one_by_one: bool) -> None:
    score, triplet = _triplet_beside_notes()
    note_ids: list[str] = _note_ids(parent=triplet)

    if one_by_one:
        for note_id in note_ids:
            delete_entities(score=score, entity_ids=[note_id])
    else:
        delete_entities(score=score, entity_ids=note_ids)

    assert score.voice.children[1] is triplet
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
    _assert_settled(score=score)


# --- nested tuplets -----------------------------------------------------------------------


def _nested(*, beside_notes: bool) -> tuple[Score, GroupRhythmicContainer, GroupRhythmicContainer]:
    """An eighth triplet on beat two whose first eighth is a sixteenth triplet; the outer
    triplet's other two eighths are notes. With ``beside_notes`` the other beats hold
    quarters."""
    score: Score = build_score(measure_count=1)
    if beside_notes:
        quarters(score=score, measure=0, beats=(0, 2, 3))
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=_Q + Fraction(index, 36),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=1,
        )
    for index in (1, 2):
        note(
            score=score,
            parent=outer,
            at=_Q + index * _THIRD,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=2,
        )

    return score, outer, inner


@pytest.mark.unit
def test_nested_tuplets_emptied_in_an_otherwise_empty_measure_are_both_removed() -> None:
    """The inner tuplet is empty with nothing around; then so is the outer one."""
    score, outer, _ = _nested(beside_notes=False)

    delete_entities(score=score, entity_ids=_note_ids(parent=outer))

    assert score.voice.children == []
    assert anchor_positions(score.measures[0]) == [Fraction(0)]
    _assert_settled(score=score)


@pytest.mark.unit
def test_nested_tuplets_emptied_beside_other_notes_both_stay_and_are_tiled() -> None:
    score, outer, inner = _nested(beside_notes=True)

    delete_entities(score=score, entity_ids=_note_ids(parent=outer))

    assert score.voice.children[1] is outer
    assert outer.children[0] is inner
    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, 3 * Fraction(1, 16), "rest", depth=2),
        slot(0, _Q + _THIRD, _Q, "rest", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    _assert_settled(score=score)


@pytest.mark.unit
def test_an_inner_tuplet_goes_while_the_outer_one_reaching_other_content_stays() -> None:
    """A quarter triplet across the barline holds an eighth triplet in its first quarter,
    all in measure one; measure two holds quarters after it. Emptied
    in one batch, the inner tuplet reaches only the empty measure and goes; the outer one
    reaches measure two and stays, tiled — and, being tiled, it wakes measure one."""
    score: Score = build_score(measure_count=2)
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(3, 4),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=Fraction(3, 4) + Fraction(index, 18),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=1,
        )
    note(
        score=score,
        parent=outer,
        at=Fraction(11, 12),
        rhythmic_value=RhythmicValue.EIGHTH,
        step=2,
    )
    note(score=score, parent=outer, at=Fraction(1), rhythmic_value=RhythmicValue.EIGHTH, step=2)
    note(
        score=score,
        parent=outer,
        at=Fraction(13, 12),
        rhythmic_value=RhythmicValue.QUARTER,
        step=2,
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))

    delete_entities(score=score, entity_ids=_note_ids(parent=outer))

    assert outer in score.voice.children
    assert inner not in outer.children
    assert shape(score=score) == Shape(
        groups=[
            GroupSlot(
                measure_index=0,
                position=Fraction(3, 4),
                written=size(RhythmicValue.QUARTER, count=3),
                occupied=size(RhythmicValue.HALF),
                depth=0,
            )
        ],
        notes=[slot(1, Fraction(beat, 4), _Q, "0") for beat in (1, 2, 3)],
        ties=[],
        rests=[(Fraction(0), Fraction(3, 4), 0), (Fraction(3, 4), Fraction(5, 4), 1)],
    )
    _assert_settled(score=score)
