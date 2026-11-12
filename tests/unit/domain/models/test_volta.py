import pytest

from piano_app.domain.score.document.models.context import (
    JumpRule,
    NewFragment,
    Volta,
    VoltaFragment,
)
from piano_app.domain.score.document.models.structural import (
    Jump,
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


def _fragment(*, end: TemporalAnchor | None, passes: set[int]) -> NewFragment:
    return NewFragment(end=end, passes=frozenset(passes))


@pytest.mark.unit
def test_a_volta_of_two_fragments_holds_the_jumps_that_play_it() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    volta: Volta = Volta.create(
        start=head,
        body_end=body_end,
        fragments=[
            _fragment(end=first_end, passes={1}),
            _fragment(end=second_end, passes={2}),
        ],
    )

    assert volta in head.starting_contexts
    assert volta.pass_count == 3
    assert [back.arrivals for back in volta.backs] == [frozenset({1}), frozenset({1})]
    assert [skip.arrivals for skip in volta.skips] == [frozenset({2}), frozenset({3})]
    assert len(head.arriving_jumps) == 2
    assert len(body_end.departing_jumps) == 2
    assert [jump.target for jump in first_end.departing_jumps] == [head]
    assert [jump.source for jump in first_end.arriving_jumps] == [body_end]
    assert [jump.target for jump in second_end.departing_jumps] == [head]
    assert [jump.source for jump in second_end.arriving_jumps] == [body_end]


@pytest.mark.unit
def test_the_fragments_are_read_back_from_the_jumps() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)
    volta: Volta = Volta.create(
        start=head,
        body_end=body_end,
        fragments=[
            _fragment(end=first_end, passes={1}),
            _fragment(end=second_end, passes={2}),
        ],
    )

    assert volta.body_end is body_end
    assert volta.fragments == (
        VoltaFragment(start=body_end, end=first_end, passes=frozenset({1})),
        VoltaFragment(start=first_end, end=second_end, passes=frozenset({2})),
    )


@pytest.mark.unit
def test_the_first_fragment_keeps_the_passes_the_later_ones_leave() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    volta: Volta = Volta.create(
        start=head,
        body_end=body_end,
        fragments=[
            _fragment(end=first_end, passes={1, 3}),
            _fragment(end=second_end, passes={2}),
        ],
    )

    assert volta.pass_count == 4
    assert [fragment.passes for fragment in volta.fragments] == [
        frozenset({1, 3}),
        frozenset({2}),
    ]
    assert [back.arrivals for back in volta.backs] == [frozenset({1, 2}), frozenset({1})]
    assert [skip.arrivals for skip in volta.skips] == [frozenset({2}), frozenset({4})]


@pytest.mark.unit
def test_a_volta_of_one_fragment_skips_it_on_the_last_pass() -> None:
    head, body_end, end = _anchors(count=3)

    volta: Volta = Volta.create(
        start=head, body_end=body_end, fragments=[_fragment(end=end, passes={1})]
    )

    assert volta.pass_count == 2
    assert [skip.arrivals for skip in volta.skips] == [frozenset({2})]
    assert [skip.jump.target for skip in volta.skips] == [end]


@pytest.mark.unit
def test_the_last_fragment_may_last_to_the_end_of_the_score() -> None:
    head, body_end, first_end = _anchors(count=3)

    volta: Volta = Volta.create(
        start=head,
        body_end=body_end,
        fragments=[
            _fragment(end=first_end, passes={1}),
            _fragment(end=None, passes={2}),
        ],
    )

    assert volta.backs[-1].jump.source is None
    assert volta.skips[-1].jump.target is None
    assert volta.fragments[-1].end is None
    assert volta.backs[-1].jump in head.arriving_jumps


@pytest.mark.unit
def test_detaching_a_volta_takes_every_jump_off_the_barlines() -> None:
    anchors: list[TemporalAnchor] = _anchors(count=4)
    head, body_end, first_end, second_end = anchors
    volta: Volta = Volta.create(
        start=head,
        body_end=body_end,
        fragments=[
            _fragment(end=first_end, passes={1}),
            _fragment(end=second_end, passes={2}),
        ],
    )

    volta.detach()

    assert volta not in head.starting_contexts
    assert all(not anchor.departing_jumps and not anchor.arriving_jumps for anchor in anchors)


@pytest.mark.unit
def test_a_volta_needs_a_fragment() -> None:
    head, body_end = _anchors(count=2)

    with pytest.raises(ValueError, match="at least one fragment"):
        Volta.create(start=head, body_end=body_end, fragments=[])


@pytest.mark.unit
def test_a_fragment_is_played_in_a_pass() -> None:
    head, body_end, end = _anchors(count=3)

    with pytest.raises(ValueError, match="at least one pass"):
        Volta.create(start=head, body_end=body_end, fragments=[_fragment(end=end, passes=set())])


@pytest.mark.unit
def test_a_pass_cannot_belong_to_two_fragments() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    with pytest.raises(ValueError, match="every pass from the first"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=first_end, passes={1, 2}),
                _fragment(end=second_end, passes={2}),
            ],
        )


@pytest.mark.unit
def test_no_pass_before_the_last_may_be_left_without_a_fragment() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    with pytest.raises(ValueError, match="every pass from the first"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=first_end, passes={1}),
                _fragment(end=second_end, passes={3}),
            ],
        )


@pytest.mark.unit
def test_the_first_pass_belongs_to_the_first_fragment() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    with pytest.raises(ValueError, match="after the first"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=first_end, passes={2}),
                _fragment(end=second_end, passes={1, 3}),
            ],
        )


@pytest.mark.unit
def test_fragments_are_first_played_in_increasing_passes() -> None:
    head, body_end, first_end, second_end, third_end = _anchors(count=5)

    with pytest.raises(ValueError, match="later pass"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=first_end, passes={1}),
                _fragment(end=second_end, passes={3}),
                _fragment(end=third_end, passes={2}),
            ],
        )


@pytest.mark.unit
def test_fragments_follow_one_another_on_the_timeline() -> None:
    head, body_end, first_end, second_end = _anchors(count=4)

    with pytest.raises(ValueError, match="end after it starts"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=second_end, passes={1}),
                _fragment(end=first_end, passes={2}),
            ],
        )


@pytest.mark.unit
def test_a_fragment_cannot_be_empty_of_music() -> None:
    head, body_end, second_end = _anchors(count=3)

    with pytest.raises(ValueError, match="another"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=body_end, passes={1}),
                _fragment(end=second_end, passes={2}),
            ],
        )


@pytest.mark.unit
def test_the_body_must_end_after_it_starts() -> None:
    first, second, end = _anchors(count=3)

    with pytest.raises(ValueError, match="body of a volta must end"):
        Volta.create(start=second, body_end=first, fragments=[_fragment(end=end, passes={1})])


@pytest.mark.unit
def test_only_the_last_fragment_may_last_to_the_end_of_the_score() -> None:
    head, body_end, second_end = _anchors(count=3)

    with pytest.raises(ValueError, match="lasts to the end"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[
                _fragment(end=None, passes={1}),
                _fragment(end=second_end, passes={2}),
            ],
        )


@pytest.mark.unit
def test_a_refused_volta_leaves_nothing_on_the_barlines() -> None:
    anchors: list[TemporalAnchor] = _anchors(count=3)
    head, body_end, end = anchors

    with pytest.raises(ValueError, match="every pass from the first"):
        Volta.create(
            start=head,
            body_end=body_end,
            fragments=[_fragment(end=end, passes={2})],
        )

    assert all(not anchor.departing_jumps and not anchor.arriving_jumps for anchor in anchors)
    assert not head.starting_contexts


@pytest.mark.unit
def test_restored_jumps_that_do_not_go_back_at_every_arrival_are_refused() -> None:
    head, body_end, end = _anchors(count=3)
    back: JumpRule = JumpRule(
        jump=Jump.unattached(source=end, target=head), arrivals=frozenset({1, 2})
    )
    skip: JumpRule = JumpRule(
        jump=Jump.unattached(source=body_end, target=end), arrivals=frozenset({2})
    )

    with pytest.raises(ValueError, match="every arrival"):
        Volta.reconstruct(id="volta", start=head, backs=[back], skips=[skip])
