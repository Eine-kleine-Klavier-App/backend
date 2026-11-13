from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import RhythmicValue

from ...scene import (
    GroupSlot,
    Score,
    Slot,
    TieSlot,
    crossing_triplet,
    group_layout,
    insert_note,
    layout,
    orphan_anchors,
    size,
    slot,
    tie_layout,
)

# The per-element overwrite rule inside a quarter triplet that crosses the barline: the
# triplet sounds [3/4, 5/4) and each of its quarters sounds 1/6 of a whole. The scene's
# triplet holds q (step 1) at 3/4, q (step 2) at 11/12 stored as e~e across the barline,
# and q (step 3) at 13/12.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _around(inside: list[Slot]) -> list[Slot]:
    """Build the scene's layout with the triplet's slots replaced by ``inside``."""
    return [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        *inside,
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]


def _assert_triplet_stays(*, score: Score) -> None:
    """Check the scene's triplet is still there, unchanged."""
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=Fraction(3, 4),
            written=size(RhythmicValue.QUARTER, count=3),
            occupied=size(RhythmicValue.HALF),
            depth=0,
        )
    ]


@pytest.mark.unit
def test_the_scene_is_a_triplet_whose_middle_quarter_is_tied_across_the_barline() -> None:
    score: Score = crossing_triplet()

    assert layout(score=score) == _around(
        [
            slot(0, Fraction(3, 4), _Q, "1", depth=1),
            slot(0, Fraction(11, 12), _E, "2", depth=1),
            slot(1, Fraction(0), _E, "2", depth=1),
            slot(1, Fraction(1, 12), _Q, "3", depth=1),
        ]
    )
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(11, 12), 2), end=(1, Fraction(0), 2))
    ]


@pytest.mark.unit
def test_a_half_over_the_tied_quarter_and_the_next_removes_everything_it_meets() -> None:
    """Cut e | dotted quarter (written): the head matches, the second piece does not.

    The second piece meets the tail of the tied quarter and the third quarter.
    """
    score: Score = crossing_triplet()

    insert_note(score=score, at=Fraction(11, 12), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == _around(
        [
            slot(0, Fraction(3, 4), _Q, "1", depth=1),
            slot(0, Fraction(11, 12), _E, "9", depth=1),
            slot(1, Fraction(0), Fraction(3, 8), "9", depth=1),
        ]
    )
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(11, 12), 9), end=(1, Fraction(0), 9))
    ]
    _assert_triplet_stays(score=score)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_the_same_quarter_over_the_tied_quarter_joins_both_pieces() -> None:
    score: Score = crossing_triplet()

    insert_note(score=score, at=Fraction(11, 12), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == _around(
        [
            slot(0, Fraction(3, 4), _Q, "1", depth=1),
            slot(0, Fraction(11, 12), _E, "2,9", depth=1),
            slot(1, Fraction(0), _E, "2,9", depth=1),
            slot(1, Fraction(1, 12), _Q, "3", depth=1),
        ]
    )
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(11, 12), 2), end=(1, Fraction(0), 2)),
        TieSlot(start=(0, Fraction(11, 12), 9), end=(1, Fraction(0), 9)),
    ]
    _assert_triplet_stays(score=score)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_dotted_quarter_ending_on_the_barline_removes_the_head_and_leaves_the_tail_untied() -> (
    None
):
    """Remove the elements met and keep the tail under the same tie, untied.

    Written 3/8, sounding [3/4, 1): meets the first quarter and the head of the tied one.
    """
    score: Score = crossing_triplet()

    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.QUARTER, dots=1)

    assert layout(score=score) == _around(
        [
            slot(0, Fraction(3, 4), Fraction(3, 8), "9", depth=1),
            slot(1, Fraction(0), _E, "2", depth=1),
            slot(1, Fraction(1, 12), _Q, "3", depth=1),
        ]
    )
    assert tie_layout(score=score) == []
    _assert_triplet_stays(score=score)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_dotted_quarter_whose_tail_alone_matches_removes_everything_it_meets() -> None:
    """Cut q | e (written): the tail matches, the first piece does not.

    Written 3/8 from 5/6; the first piece meets the first quarter and the head of the tied
    one, the second lands on the tail.
    """
    score: Score = crossing_triplet()

    insert_note(score=score, at=Fraction(5, 6), rhythmic_value=RhythmicValue.QUARTER, dots=1)

    assert layout(score=score) == _around(
        [
            slot(0, Fraction(3, 4), _E, "rest", depth=1),
            slot(0, Fraction(5, 6), _Q, "9", depth=1),
            slot(1, Fraction(0), _E, "9", depth=1),
            slot(1, Fraction(1, 12), _Q, "3", depth=1),
        ]
    )
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(5, 6), 9), end=(1, Fraction(0), 9))
    ]
    _assert_triplet_stays(score=score)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_voice_level_half_meeting_the_triplet_removes_it_whole_across_the_barline() -> None:
    """Remove the triplet as one element, its measure-2 part included."""
    score: Score = crossing_triplet()

    insert_note(score=score, at=Fraction(1, 2), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), Fraction(1, 2), "9"),
        slot(1, Fraction(0), _Q, "rest"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []
