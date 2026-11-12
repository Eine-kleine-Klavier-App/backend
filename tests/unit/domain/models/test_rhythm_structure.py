from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)

from ..scene import Score, anchor_at, build_score, eighth_triplet, group, note, size

# The rhythm structure after "every container starts at its own anchor": a group is placed
# by its anchor, not by its first child, and the anchor indexes every container starting
# at it — leaves and groups alike.


# --- Measure.holds ------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("position", "inside"),
    [
        (Fraction(0), True),
        (Fraction(3, 4), True),
        (Fraction(63, 64), True),
        (Fraction(1), False),  # the end of a measure is the start of the next one
        (Fraction(5, 4), False),
    ],
)
def test_a_measure_holds_positions_from_its_start_up_to_but_not_including_its_end(
    position: Fraction,
    inside: bool,
) -> None:
    measure: Measure = Measure.create()

    assert measure.holds(position=MeasurePosition.of_fraction(fraction=position)) is inside


@pytest.mark.unit
def test_a_measure_holds_positions_by_its_own_time_signature() -> None:
    three_four: Measure = Measure.create(time_signature=size(RhythmicValue.QUARTER, count=3))

    assert three_four.holds(position=MeasurePosition.of(numerator=1, denominator=2))
    assert not three_four.holds(position=MeasurePosition.of(numerator=3, denominator=4))


@pytest.mark.unit
def test_an_anchor_outside_its_measure_is_refused_by_the_measure() -> None:
    measure: Measure = Measure.create()

    with pytest.raises(ValueError, match="at or beyond the end"):
        TemporalAnchor.create(
            measure=measure, position=MeasurePosition.of_fraction(fraction=Fraction(1))
        )


# --- every container starts at its own anchor ----------------------------------------


@pytest.mark.unit
def test_a_leaf_starts_at_the_anchor_it_was_given() -> None:
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(1, 4))

    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.voice,
        anchor=anchor,
        size=size(RhythmicValue.QUARTER),
    )

    assert leaf.start_anchor is anchor
    assert leaf.anchor is anchor


@pytest.mark.unit
def test_a_group_starts_at_its_own_anchor_while_empty() -> None:
    score: Score = build_score(measure_count=1)

    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1, 4),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    assert triplet.children == []
    assert triplet.start_anchor is anchor_at(score=score, at=Fraction(1, 4))


@pytest.mark.unit
def test_a_group_keeps_its_anchor_when_its_first_child_goes() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score,
        parent=score.voice,
        at=Fraction(1, 4),
    )
    start: TemporalAnchor = triplet.start_anchor

    first = triplet.children[0]
    first.detach()

    assert triplet.start_anchor is start
    assert triplet.children[0].start_anchor is anchor_at(
        score=score,
        at=Fraction(1, 4) + Fraction(1, 12),
    )


@pytest.mark.unit
def test_an_empty_group_can_join_a_voice_that_already_has_content() -> None:
    """Before groups had an anchor of their own, ordering an empty group among its
    siblings read its first child and failed."""
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )

    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1, 4),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    assert score.voice.children[1] is triplet
    assert len(score.voice.children) == 3


@pytest.mark.unit
def test_children_join_a_group_in_timeline_order_whatever_order_they_come_in() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    for index in (2, 0, 1):
        note(
            score=score,
            parent=triplet,
            at=Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index,
        )

    assert [child.start_anchor.position.value for child in triplet.children] == [
        Fraction(0),
        Fraction(1, 12),
        Fraction(2, 12),
    ]


@pytest.mark.unit
def test_a_group_still_refuses_children_past_its_written_size() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(0)
    )

    with pytest.raises(ValueError, match="exceeds its written size"):
        LeafRhythmicContainer.create(
            parent=triplet,
            anchor=anchor_at(score=score, at=Fraction(1, 8)),
            size=size(RhythmicValue.EIGHTH),
        )

    assert len(triplet.children) == 3


@pytest.mark.unit
def test_a_group_that_scales_nothing_is_refused() -> None:
    score: Score = build_score(measure_count=1)

    with pytest.raises(ValueError, match="differ in written and occupied size"):
        group(
            score=score,
            parent=score.voice,
            at=Fraction(0),
            written=size(RhythmicValue.QUARTER, count=2),
            occupied=size(RhythmicValue.HALF),
        )

    assert score.voice.children == []


# --- the anchor's container index ----------------------------------------------------


@pytest.mark.unit
def test_an_anchor_indexes_every_container_starting_at_it_across_scopes() -> None:
    """A group, a group nested in it and a leaf nested in that, all starting together,
    share one anchor and are all on it."""
    score: Score = build_score(measure_count=1)
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
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=inner,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.SIXTEENTH,
        step=0,
    )

    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    assert set(anchor.containers) == {outer, inner, leaf}
    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_detaching_a_container_takes_it_off_its_anchor() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(0)
    )
    anchor: TemporalAnchor = triplet.start_anchor
    first = triplet.children[0]

    first.detach()

    assert list(anchor.containers) == [triplet]


@pytest.mark.unit
def test_an_anchor_holding_only_a_group_is_not_an_orphan() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(0)
    )
    anchor: TemporalAnchor = triplet.start_anchor

    triplet.children[0].detach()

    assert not anchor.is_orphan


@pytest.mark.unit
def test_an_anchor_is_an_orphan_once_its_last_container_is_gone() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1, 4),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    anchor: TemporalAnchor = triplet.start_anchor

    triplet.detach()

    assert anchor.is_orphan
    assert score.voice.children == []


@pytest.mark.unit
def test_an_anchor_refuses_a_container_starting_elsewhere() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    elsewhere: TemporalAnchor = anchor_at(score=score, at=Fraction(1, 2))

    with pytest.raises(ValueError, match="starting at a different anchor"):
        elsewhere.add_container(container=leaf)

    assert elsewhere.containers == []
