import pytest

from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)


def _anchors(*, count: int) -> list[TemporalAnchor]:
    """Anchors one eighth apart in one measure, in timeline order."""
    measure: Measure = Measure.create()
    return [
        TemporalAnchor.create(
            measure=measure, position=MeasurePosition.of(numerator=index, denominator=8)
        )
        for index in range(count)
    ]


@pytest.mark.unit
def test_a_refrain_owns_a_jump_back_from_its_end_to_its_start() -> None:
    start, end = _anchors(count=2)

    refrain: Refrain = Refrain.create(start=start, end=end, times=3)

    assert refrain in start.starting_contexts
    assert refrain.jump.source is end
    assert refrain.jump.target is start
    assert refrain.jump in end.departing_jumps
    assert refrain.jump in start.arriving_jumps
    assert refrain.end is end
    assert refrain.times == 3


@pytest.mark.unit
def test_a_refrain_may_close_the_piece() -> None:
    (start,) = _anchors(count=1)

    refrain: Refrain = Refrain.create(start=start, end=None, times=2)

    assert refrain.end is None
    assert refrain.jump in start.arriving_jumps


@pytest.mark.unit
def test_the_jump_is_taken_on_every_arrival_but_the_last() -> None:
    start, end = _anchors(count=2)
    refrain: Refrain = Refrain.create(start=start, end=end, times=3)

    fires: list[bool] = [refrain.fires_on(arrival=arrival) for arrival in (0, 1, 2, 3, 4)]

    assert fires == [False, True, True, False, False]


@pytest.mark.unit
def test_a_refrain_is_played_at_least_twice() -> None:
    start, end = _anchors(count=2)

    with pytest.raises(ValueError, match="at least twice"):
        Refrain.create(start=start, end=end, times=1)

    assert not start.arriving_jumps
    assert not end.departing_jumps


@pytest.mark.unit
def test_a_refrain_must_end_after_it_starts() -> None:
    start, end = _anchors(count=2)

    with pytest.raises(ValueError, match="end after it starts"):
        Refrain.create(start=end, end=start, times=2)

    assert not start.departing_jumps
    assert not end.arriving_jumps


@pytest.mark.unit
def test_detaching_a_refrain_takes_its_jump_off_the_barlines() -> None:
    start, end = _anchors(count=2)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    refrain.detach()

    assert refrain not in start.starting_contexts
    assert refrain.jump not in start.arriving_jumps
    assert refrain.jump not in end.departing_jumps


@pytest.mark.unit
def test_changing_the_times_keeps_the_refrain() -> None:
    start, end = _anchors(count=2)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    refrain.set_times(times=4)

    assert refrain.times == 4

    with pytest.raises(ValueError, match="at least twice"):
        refrain.set_times(times=1)

    assert refrain.times == 4


@pytest.mark.unit
def test_moving_the_end_moves_the_jump() -> None:
    start, end, later = _anchors(count=3)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    refrain.set_end(end=later)
    end_after_moving: TemporalAnchor | None = refrain.end

    refrain.set_end(end=None)
    end_after_closing_the_piece: TemporalAnchor | None = refrain.end

    assert end_after_moving is later
    assert end_after_closing_the_piece is None
    assert refrain.jump not in end.departing_jumps
    assert refrain.jump not in later.departing_jumps


@pytest.mark.unit
def test_the_end_cannot_move_before_the_start() -> None:
    first, start, end = _anchors(count=3)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    with pytest.raises(ValueError, match="end after it starts"):
        refrain.set_end(end=first)

    assert refrain.end is end


@pytest.mark.unit
def test_moving_the_start_moves_the_landing_of_the_jump() -> None:
    first, start, end = _anchors(count=3)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    refrain.set_start(start=first)

    assert refrain.start is first
    assert refrain.jump.target is first
    assert refrain in first.starting_contexts
    assert refrain not in start.starting_contexts
    assert refrain.jump in first.arriving_jumps
    assert refrain.jump not in start.arriving_jumps
    assert refrain.jump in end.departing_jumps


@pytest.mark.unit
def test_the_start_cannot_move_past_the_end() -> None:
    start, end, later = _anchors(count=3)
    refrain: Refrain = Refrain.create(start=start, end=end, times=2)

    with pytest.raises(ValueError, match="end after it starts"):
        refrain.set_start(start=later)

    assert refrain.start is start
    assert refrain.jump.target is start
