from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithRestIntent,
)

from ...scene import (
    GroupSlot,
    Score,
    TieSlot,
    apply_intent,
    build_score,
    create_tuplet_with_note,
    group_layout,
    insert_note,
    layout,
    orphan_anchors,
    quarters,
    size,
    slot,
    tie_layout,
    value,
)

# A tuplet created with a first element that crosses a barline: the element is cut at the
# barline inside the tuplet (note pieces tied, rest pieces untied) and the rest of the
# interior is tiled with rests. The expected layouts are those of the two-step workaround
# (create the tuplet with a short first note, then insert the long one into it), which the
# companion tests reach today.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _two_measures_of_quarters() -> Score:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    return score


def _assert_quarter_triplet_starting_with_a_half(*, score: Score) -> None:
    """Check a quarter triplet on beat four whose first half is cut 3/8 | 1/8 (written).

    The triplet sounds [3/4, 5/4); its first half sounds [3/4, 13/12); a quarter rest fills
    the triplet's end.
    """
    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), Fraction(3, 8), "9", depth=1),
        slot(1, Fraction(0), _E, "9", depth=1),
        slot(1, Fraction(1, 12), _Q, "rest", depth=1),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 9), end=(1, Fraction(0), 9))
    ]
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=Fraction(3, 4),
            written=size(RhythmicValue.QUARTER, count=3),
            occupied=size(RhythmicValue.HALF),
            depth=0,
        )
    ]
    assert orphan_anchors(score=score) == []


def _assert_eighth_triplet_starting_with_a_quarter(*, score: Score) -> None:
    """Check an eighth triplet on the last eighth whose first quarter is cut 3/16 | 1/16.

    The triplet sounds [7/8, 9/8) and displaces both quarters it touches; its first quarter
    (written) sounds [7/8, 25/24).
    """
    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _E, "rest"),
        slot(0, Fraction(7, 8), Fraction(3, 16), "9", depth=1),
        slot(1, Fraction(0), Fraction(1, 16), "9", depth=1),
        slot(1, Fraction(1, 24), _E, "rest", depth=1),
        slot(1, _E, _E, "rest"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(7, 8), 9), end=(1, Fraction(0), 9))
    ]
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=Fraction(7, 8),
            written=size(RhythmicValue.EIGHTH, count=3),
            occupied=size(RhythmicValue.QUARTER),
            depth=0,
        )
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_quarter_triplet_on_beat_four_may_start_with_a_half() -> None:
    score: Score = _two_measures_of_quarters()

    create_tuplet_with_note(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.HALF),
    )

    _assert_quarter_triplet_starting_with_a_half(score=score)


@pytest.mark.unit
def test_a_quarter_triplet_on_beat_four_reaches_a_first_half_in_two_steps() -> None:
    """Create the triplet with a first quarter, then insert the half over it."""
    score: Score = _two_measures_of_quarters()

    create_tuplet_with_note(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
        step=5,
    )
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    _assert_quarter_triplet_starting_with_a_half(score=score)


@pytest.mark.unit
def test_an_eighth_triplet_on_the_last_eighth_may_start_with_a_quarter() -> None:
    score: Score = _two_measures_of_quarters()

    create_tuplet_with_note(
        score=score,
        at=Fraction(7, 8),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        first=value(RhythmicValue.QUARTER),
    )

    _assert_eighth_triplet_starting_with_a_quarter(score=score)


@pytest.mark.unit
def test_an_eighth_triplet_on_the_last_eighth_reaches_a_first_quarter_in_two_steps() -> None:
    """Create the triplet with a first eighth, then insert the quarter over it."""
    score: Score = _two_measures_of_quarters()

    create_tuplet_with_note(
        score=score,
        at=Fraction(7, 8),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        first=value(RhythmicValue.EIGHTH),
        step=5,
    )
    insert_note(score=score, at=Fraction(7, 8), rhythmic_value=RhythmicValue.QUARTER)

    _assert_eighth_triplet_starting_with_a_quarter(score=score)


@pytest.mark.unit
def test_a_half_rest_opening_a_quarter_triplet_on_beat_four_is_cut_untied_and_kept() -> None:
    """The first rest, a written half, is cut at the barline like a note but without a tie
    (3/8 | 1/8 written). No intent inserts a rest, so there is no two-step companion.

    Before the barline the 3/8 piece fills the triplet's part of the measure; after it the
    1/8 piece keeps its value and the hole left over is filled with a quarter rest of its
    own.
    """
    score: Score = _two_measures_of_quarters()

    apply_intent(
        score=score,
        intent=CreateTupletWithRestIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[0].id,
            position=MeasurePosition.of_fraction(fraction=Fraction(3, 4)),
            written_size=size(RhythmicValue.QUARTER, count=3),
            occupied_size=size(RhythmicValue.HALF),
            written_value=value(RhythmicValue.HALF),
        ),
    )

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), Fraction(3, 8), "rest", depth=1),
        slot(1, Fraction(0), _E, "rest", depth=1),
        slot(1, Fraction(1, 12), _Q, "rest", depth=1),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == []
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=Fraction(3, 4),
            written=size(RhythmicValue.QUARTER, count=3),
            occupied=size(RhythmicValue.HALF),
            depth=0,
        )
    ]
    assert orphan_anchors(score=score) == []
