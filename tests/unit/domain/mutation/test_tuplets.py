from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation import build_engine
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteRhythmicGroupRequest,
)

from ..scene import (
    NEW_STEP,
    Score,
    Slot,
    build_score,
    delete_entities,
    eighth_triplet,
    group,
    insert_note,
    layout,
    note,
    orphan_anchors,
    quarters,
    size,
    slot,
)

# The tuplet operations the model supports now that a group starts at its own anchor:
# a hole anywhere inside a group moves no sibling, so deleting and replacing notes in a
# tuplet keeps every other note where it was.
#
# The scene: a quarter, an eighth triplet on beat two (staff steps 1, 2, 3), two quarters.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


def _scene() -> tuple[Score, GroupRhythmicContainer]:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, bar=0, beats=(2, 3))

    return score, triplet


def _note_ids(*, triplet: GroupRhythmicContainer, indices: list[int]) -> list[str]:
    ids: list[str] = []
    for index in indices:
        leaf = triplet.children[index]
        assert isinstance(leaf, LeafRhythmicContainer)
        assert isinstance(leaf.carrier, NoteCarrier)
        ids.append(leaf.carrier.notes[0].id)

    return ids


def _around(inside: list[Slot]) -> list[Slot]:
    """The scene's layout with the triplet's slots replaced by ``inside``."""
    return [
        slot(0, Fraction(0), _Q, "0"),
        *inside,
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("deleted", "contents"),
    [
        (0, ["rest", "2", "3"]),
        (1, ["1", "rest", "3"]),
        (2, ["1", "2", "rest"]),
    ],
)
def test_deleting_one_note_of_a_triplet_leaves_a_rest_in_its_place_only(
    deleted: int,
    contents: list[str],
) -> None:
    score, triplet = _scene()
    start: TemporalAnchor = triplet.start_anchor

    delete_entities(score=score, entity_ids=_note_ids(triplet=triplet, indices=[deleted]))

    assert layout(score=score) == _around(
        [
            slot(0, _Q + index * _THIRD, _E, content, depth=1)
            for index, content in enumerate(contents)
        ]
    )
    assert triplet.start_anchor is start
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_two_notes_of_a_triplet_keeps_the_third_in_place() -> None:
    score, triplet = _scene()

    delete_entities(score=score, entity_ids=_note_ids(triplet=triplet, indices=[0, 2]))

    assert [entry.content for entry in layout(score=score)[1:4]] == ["rest", "2", "rest"]
    assert layout(score=score)[2] == slot(0, _Q + _THIRD, _E, "2", depth=1)


@pytest.mark.unit
def test_deleting_every_note_of_a_triplet_at_once_removes_the_triplet() -> None:
    """Left without children, the triplet is removed; its room becomes a gap of the voice
    and is filled with a quarter rest."""
    score, triplet = _scene()

    delete_entities(score=score, entity_ids=_note_ids(triplet=triplet, indices=[0, 1, 2]))

    assert layout(score=score) == _around([slot(0, _Q, _Q, "rest")])
    assert triplet not in score.voice.children
    assert orphan_anchors(score=score) == []
    assert len(score.measures[0].anchors) == 4


@pytest.mark.unit
def test_deleting_the_notes_of_a_triplet_one_by_one_leaves_a_triplet_of_rests() -> None:
    """Each hole is filled before the next delete, so the triplet never goes empty — and a
    triplet of rests is valid."""
    score, triplet = _scene()
    note_ids: list[str] = _note_ids(triplet=triplet, indices=[0, 1, 2])

    for note_id in note_ids:
        delete_entities(score=score, entity_ids=[note_id])

    assert score.voice.children[1] is triplet
    assert layout(score=score) == _around(
        [slot(0, _Q + index * _THIRD, _E, "rest", depth=1) for index in range(3)]
    )


@pytest.mark.unit
def test_replacing_the_first_note_with_a_longer_one_displaces_only_what_it_covers() -> None:
    """A written quarter from the triplet's start covers its first two eighths; the third
    keeps its place."""
    score, _triplet = _scene()

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == _around(
        [
            slot(0, _Q, _Q, str(NEW_STEP), depth=1),
            slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        ]
    )


@pytest.mark.unit
def test_a_same_size_note_inside_a_triplet_joins_the_note_there() -> None:
    score, _triplet = _scene()

    insert_note(score=score, at=_Q + _THIRD, rhythmic_value=RhythmicValue.EIGHTH)

    assert [entry.content for entry in layout(score=score)[1:4]] == ["1", f"2,{NEW_STEP}", "3"]


@pytest.mark.unit
def test_a_shorter_note_inside_a_triplet_leaves_the_rest_of_the_slot_as_a_rest() -> None:
    """A written sixteenth in the triplet sounds 1/24; the remaining sixteenth of the
    middle eighth is filled, and the neighbours do not move."""
    score, _triplet = _scene()

    insert_note(score=score, at=_Q + _THIRD, rhythmic_value=RhythmicValue.SIXTEENTH)

    assert layout(score=score) == _around(
        [
            slot(0, _Q, _E, "1", depth=1),
            slot(0, _Q + _THIRD, Fraction(1, 16), str(NEW_STEP), depth=1),
            slot(0, _Q + _THIRD + Fraction(1, 24), Fraction(1, 16), "rest", depth=1),
            slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        ]
    )


@pytest.mark.unit
def test_deleting_a_whole_triplet_gives_its_room_back_to_the_voice() -> None:
    """The voice's rest takes the triplet's place on the triplet's own anchor; the
    anchors of its inner notes are reaped."""
    score, triplet = _scene()
    start: TemporalAnchor = triplet.start_anchor

    build_engine().process(
        document=score.document,
        requests=[DeleteRhythmicGroupRequest(target=triplet)],
    )

    assert layout(score=score) == _around([slot(0, _Q, _Q, "rest")])
    assert score.measures[0].anchors[1] is start
    assert len(score.measures[0].anchors) == 4


@pytest.mark.unit
def test_deleting_the_only_triplet_of_a_voice_reaps_its_anchor() -> None:
    """With nothing else in the bar, the voice no longer reaches it: no rest wakes it, and
    every anchor of the triplet goes."""
    score: Score = build_score(bars=1)
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)

    build_engine().process(
        document=score.document,
        requests=[DeleteRhythmicGroupRequest(target=triplet)],
    )

    assert score.voice.children == []
    assert score.measures[0].anchors == []


@pytest.mark.unit
def test_a_hole_in_a_triplet_crossing_a_barline_moves_nothing_in_either_bar() -> None:
    """A quarter triplet from beat four: its notes sit at 3/4 and 11/12 of the first bar
    and 1/12 of the second. Deleting the middle one leaves the last in the next bar."""
    score: Score = build_score(bars=2)
    quarters(score=score, bar=0, beats=(0, 1, 2))
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    for index in range(3):
        note(
            score=score,
            parent=triplet,
            at=Fraction(3, 4) + Fraction(index, 6),
            rhythmic_value=RhythmicValue.QUARTER,
            step=index + 1,
        )
    quarters(score=score, bar=1, beats=(1, 2, 3))

    delete_entities(score=score, entity_ids=_note_ids(triplet=triplet, indices=[1]))

    assert layout(score=score)[3:6] == [
        slot(0, Fraction(3, 4), _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _Q, "rest", depth=1),
        slot(1, Fraction(1, 12), _Q, "3", depth=1),
    ]


@pytest.mark.unit
def test_a_hole_in_a_nested_triplet_moves_nothing_at_either_depth() -> None:
    score: Score = build_score(bars=1)
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(0),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=Fraction(index, 36),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=index + 1,
        )
    for index in (1, 2):
        note(
            score=score,
            parent=outer,
            at=Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 3,
        )
    quarters(score=score, bar=0, beats=(1, 2, 3))

    delete_entities(score=score, entity_ids=_note_ids(triplet=inner, indices=[0]))

    assert layout(score=score)[:5] == [
        slot(0, Fraction(0), Fraction(1, 16), "rest", depth=2),
        slot(0, Fraction(1, 36), Fraction(1, 16), "2", depth=2),
        slot(0, Fraction(2, 36), Fraction(1, 16), "3", depth=2),
        slot(0, Fraction(1, 12), _E, "4", depth=1),
        slot(0, Fraction(2, 12), _E, "5", depth=1),
    ]
    assert inner.start_anchor is outer.start_anchor


@pytest.mark.unit
def test_a_delete_inside_a_triplet_rolls_back_to_the_exact_triplet() -> None:
    score, triplet = _scene()
    before: list[Slot] = layout(score=score)

    log: MutationLog = delete_entities(
        score=score,
        entity_ids=_note_ids(triplet=triplet, indices=[0, 1, 2]),
    )
    log.rollback()

    assert layout(score=score) == before
    assert len(triplet.children) == 3


# --- empty groups at the gesture boundary --------------------------------------------------


@pytest.mark.unit
def test_an_empty_group_nested_in_a_triplet_is_removed_and_its_slot_rested() -> None:
    score, triplet = _scene()
    first = triplet.children[0]
    assert isinstance(first, LeafRhythmicContainer)
    first.detach()
    group(
        score=score,
        parent=triplet,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )

    build_engine().process(document=score.document, requests=[])

    assert [type(child) for child in triplet.children] == [LeafRhythmicContainer] * 3
    assert layout(score=score)[1] == slot(0, _Q, _E, "rest", depth=1)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_an_empty_group_alone_in_its_bar_is_removed_and_the_bar_stays_empty() -> None:
    score: Score = build_score(bars=1)
    group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    build_engine().process(document=score.document, requests=[])

    assert score.voice.children == []
    assert score.measures[0].anchors == []
