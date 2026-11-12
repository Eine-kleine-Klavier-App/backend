import pytest

from piano_app.domain.score.document.models.structural import (
    Jump,
    Measure,
    MeasurePosition,
    TemporalAnchor,
)


@pytest.fixture
def anchor() -> TemporalAnchor:
    measure: Measure = Measure.create()
    position: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)
    return TemporalAnchor.create(measure=measure, position=position)


@pytest.fixture
def another_anchor(anchor: TemporalAnchor) -> TemporalAnchor:
    position: MeasurePosition = MeasurePosition.of(numerator=1, denominator=2)
    return TemporalAnchor.create(measure=anchor.measure, position=position)


@pytest.fixture
def third_anchor(anchor: TemporalAnchor) -> TemporalAnchor:
    position: MeasurePosition = MeasurePosition.of(numerator=3, denominator=4)
    return TemporalAnchor.create(measure=anchor.measure, position=position)


@pytest.mark.unit
def test_a_jump_is_listed_where_it_leaves_and_where_it_lands(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    assert jump in anchor.departing_jumps
    assert jump in another_anchor.arriving_jumps


@pytest.mark.unit
def test_detaching_a_jump_removes_it_at_both_barlines(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    jump.detach()

    assert jump not in anchor.departing_jumps
    assert jump not in another_anchor.arriving_jumps


@pytest.mark.unit
def test_a_jump_may_land_before_the_place_it_leaves_from(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=another_anchor, target=anchor)

    assert jump.target is anchor
    assert jump in anchor.arriving_jumps


@pytest.mark.unit
def test_a_jump_may_leave_from_the_end_of_the_score(anchor: TemporalAnchor) -> None:
    jump: Jump = Jump.create(source=None, target=anchor)

    assert jump.source is None
    assert jump in anchor.arriving_jumps


@pytest.mark.unit
def test_a_jump_may_land_at_the_end_of_the_score(anchor: TemporalAnchor) -> None:
    jump: Jump = Jump.create(source=anchor, target=None)

    assert jump.target is None
    assert jump in anchor.departing_jumps


@pytest.mark.unit
def test_a_jump_cannot_leave_and_land_at_the_same_barline(anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="another"):
        Jump.create(source=anchor, target=anchor)


@pytest.mark.unit
def test_a_jump_cannot_go_from_the_end_of_the_score_to_the_end_of_the_score() -> None:
    with pytest.raises(ValueError, match="not both"):
        Jump.create(source=None, target=None)


@pytest.mark.unit
def test_changing_the_landing_moves_the_jump_to_the_new_barline(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    third_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    jump.set_target(target=third_anchor)

    assert jump.target is third_anchor
    assert jump not in another_anchor.arriving_jumps
    assert jump in third_anchor.arriving_jumps


@pytest.mark.unit
def test_changing_the_departure_moves_the_jump_to_the_new_barline(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    third_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    jump.set_source(source=third_anchor)

    assert jump.source is third_anchor
    assert jump not in anchor.departing_jumps
    assert jump in third_anchor.departing_jumps
    assert jump in another_anchor.arriving_jumps


@pytest.mark.unit
def test_the_end_of_the_score_can_become_a_barline_and_back(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=None, target=anchor)

    jump.set_source(source=another_anchor)
    assert jump in another_anchor.departing_jumps

    jump.set_source(source=None)
    assert jump not in another_anchor.departing_jumps
    assert jump.source is None


@pytest.mark.unit
def test_changing_an_end_onto_the_other_one_is_refused_and_changes_nothing(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    with pytest.raises(ValueError, match="another"):
        jump.set_target(target=anchor)

    with pytest.raises(ValueError, match="another"):
        jump.set_source(source=another_anchor)

    assert jump.target is another_anchor
    assert jump.source is anchor
    assert jump in another_anchor.arriving_jumps
    assert jump in anchor.departing_jumps


@pytest.mark.unit
def test_a_barline_a_jump_touches_is_not_an_orphan(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    orphans_before: tuple[bool, bool] = (anchor.is_orphan, another_anchor.is_orphan)

    jump: Jump = Jump.create(source=anchor, target=another_anchor)
    orphans_with_jump: tuple[bool, bool] = (anchor.is_orphan, another_anchor.is_orphan)

    jump.detach()
    orphans_after: tuple[bool, bool] = (anchor.is_orphan, another_anchor.is_orphan)

    assert orphans_before == (True, True)
    assert orphans_with_jump == (False, False)
    assert orphans_after == (True, True)


@pytest.mark.unit
def test_a_barline_refuses_a_jump_that_does_not_touch_it(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    third_anchor: TemporalAnchor,
) -> None:
    jump: Jump = Jump.create(source=anchor, target=another_anchor)

    with pytest.raises(ValueError, match="does not land"):
        third_anchor.add_arriving_jump(jump=jump)

    with pytest.raises(ValueError, match="does not leave"):
        third_anchor.add_departing_jump(jump=jump)
