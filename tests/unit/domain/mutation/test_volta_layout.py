from fractions import Fraction

import pytest

from piano_app.domain.score.document.services.contexts.volta_layout import (
    Boundary,
    Fragment,
    Layout,
    append_fragment,
    collapse,
    move_boundary,
    move_start,
    set_passes,
    split_last_fragment,
)

# A layout is written by the places its parts end at, whole numbers or halves; the place stands
# for itself, so the places are compared as they are.


def _at(place: int | Fraction) -> Boundary[Fraction]:
    return Boundary(position=Fraction(place), ref=Fraction(place))


def _layout(
    *, fragments: list[tuple[int | Fraction, set[int]]], body_end: int = 1
) -> Layout[Fraction]:
    return Layout(
        start=_at(0),
        body_end=_at(body_end),
        fragments=tuple(
            Fragment(end=_at(end), passes=frozenset(passes)) for end, passes in fragments
        ),
    )


def _read(layout: Layout[Fraction] | None) -> tuple[int, list[tuple[Fraction, set[int]]]] | None:
    if layout is None:
        return None

    return (
        int(layout.body_end.position),
        [(fragment.end.position, set(fragment.passes)) for fragment in layout.fragments],
    )


# the endings [1., 3. and [2. of four passes, the body being measure 0 and the fragments 1 and 2
_FOUR: list[tuple[int | Fraction, set[int]]] = [(2, {1, 3}), (3, {2})]


@pytest.mark.unit
def test_stretching_a_fragment_over_the_next_absorbs_it_and_shifts_the_later_passes() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=1, to=_at(3)
    )

    assert _read(moved) == (1, [(Fraction(3), {1, 2})])


@pytest.mark.unit
def test_stretching_a_fragment_left_over_the_one_before_absorbs_that_one() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=1, to=_at(1)
    )

    assert _read(moved) == (1, [(Fraction(3), {1})])


@pytest.mark.unit
def test_moving_a_boundary_inside_the_parts_around_it_absorbs_nothing() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=1, to=_at(Fraction(3, 2))
    )

    assert _read(moved) == (1, [(Fraction(3, 2), {1, 3}), (Fraction(3), {2})])


@pytest.mark.unit
def test_the_body_stretched_over_a_fragment_absorbs_it() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=0, to=_at(2)
    )

    assert _read(moved) == (2, [(Fraction(3), {1})])


@pytest.mark.unit
def test_the_body_stretched_over_every_fragment_leaves_no_volta() -> None:
    assert move_boundary(layout=_layout(fragments=_FOUR), index=0, to=_at(3)) is None


@pytest.mark.unit
def test_the_body_shrinks_to_something_but_not_to_nothing() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR, body_end=2), index=0, to=_at(1)
    )

    assert _read(moved) == (1, [(Fraction(2), {1, 3}), (Fraction(3), {2})])

    with pytest.raises(ValueError, match="body of a volta must end"):
        move_boundary(layout=_layout(fragments=_FOUR), index=0, to=_at(0))


@pytest.mark.unit
def test_a_fragment_stretched_far_left_shrinks_the_body_after_absorbing_what_it_covers() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR, body_end=2), index=1, to=_at(1)
    )

    assert _read(moved) == (1, [(Fraction(3), {1})])


@pytest.mark.unit
def test_stretching_far_right_absorbs_every_fragment_after() -> None:
    moved: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=1, to=_at(5)
    )

    assert _read(moved) == (1, [(Fraction(5), {1, 2})])


@pytest.mark.unit
def test_the_end_of_the_last_fragment_moves_alone() -> None:
    longer: Layout[Fraction] | None = move_boundary(
        layout=_layout(fragments=_FOUR), index=2, to=_at(4)
    )

    assert _read(longer) == (1, [(Fraction(2), {1, 3}), (Fraction(4), {2})])

    with pytest.raises(ValueError, match="must end after it starts"):
        move_boundary(layout=_layout(fragments=_FOUR), index=2, to=_at(2))


@pytest.mark.unit
def test_a_boundary_that_does_not_exist_is_refused() -> None:
    with pytest.raises(ValueError, match="no such boundary"):
        move_boundary(layout=_layout(fragments=_FOUR), index=3, to=_at(4))


@pytest.mark.unit
def test_the_start_of_the_body_moves_alone_and_stays_before_its_end() -> None:
    moved: Layout[Fraction] = move_start(layout=_layout(fragments=_FOUR, body_end=2), to=_at(1))

    assert moved.start.position == 1

    with pytest.raises(ValueError, match="body of a volta must end"):
        move_start(layout=_layout(fragments=_FOUR), to=_at(1))


@pytest.mark.unit
def test_naming_a_pass_takes_it_from_the_first_fragment() -> None:
    moved: Layout[Fraction] = set_passes(
        layout=_layout(fragments=_FOUR), index=1, passes=frozenset({2, 3})
    )

    assert _read(moved) == (1, [(Fraction(2), {1}), (Fraction(3), {2, 3})])


@pytest.mark.unit
def test_naming_a_pass_beyond_the_last_stored_one_makes_the_volta_longer() -> None:
    moved: Layout[Fraction] = set_passes(
        layout=_layout(fragments=_FOUR), index=1, passes=frozenset({2, 4})
    )

    assert _read(moved) == (1, [(Fraction(2), {1, 3}), (Fraction(3), {2, 4})])
    assert moved.stored_passes == 4


@pytest.mark.unit
def test_the_passes_of_a_fragment_are_refused_when_they_break_the_order() -> None:
    three_parts: Layout[Fraction] = _layout(fragments=[(2, {1}), (3, {2}), (4, {3})])

    # the third fragment would be left with no pass
    with pytest.raises(ValueError, match="at least one pass"):
        set_passes(layout=three_parts, index=1, passes=frozenset({3}))

    with pytest.raises(ValueError, match="later pass"):
        set_passes(layout=three_parts, index=1, passes=frozenset({4}))

    with pytest.raises(ValueError, match="at least one pass"):
        set_passes(layout=three_parts, index=1, passes=frozenset())

    with pytest.raises(ValueError, match="played in the passes the others leave"):
        set_passes(layout=three_parts, index=0, passes=frozenset({1}))

    with pytest.raises(ValueError, match="after the first"):
        set_passes(layout=three_parts, index=2, passes=frozenset({1}))


@pytest.mark.unit
def test_a_fragment_added_after_the_last_takes_the_last_pass() -> None:
    longer: Layout[Fraction] = append_fragment(layout=_layout(fragments=_FOUR), end=_at(4))

    assert _read(longer) == (
        1,
        [(Fraction(2), {1, 3}), (Fraction(3), {2}), (Fraction(4), {4})],
    )

    with pytest.raises(ValueError, match="must end after it starts"):
        append_fragment(layout=_layout(fragments=_FOUR), end=_at(3))


@pytest.mark.unit
def test_the_last_fragment_cut_in_two_gives_the_rest_the_last_pass() -> None:
    cut: Layout[Fraction] = split_last_fragment(
        layout=_layout(fragments=[(2, {1}), (4, {2})]), at=_at(3)
    )

    assert _read(cut) == (1, [(Fraction(2), {1}), (Fraction(3), {2}), (Fraction(4), {3})])

    with pytest.raises(ValueError, match="cut inside the last fragment"):
        split_last_fragment(layout=_layout(fragments=[(2, {1}), (4, {2})]), at=_at(2))


@pytest.mark.unit
def test_drawing_a_boundary_onto_the_next_leaves_the_fragment_between_with_no_length() -> None:
    drawn: Layout[Fraction] | None = collapse(
        layout=_layout(fragments=_FOUR), inside=lambda ref: ref == 1, to=_at(2)
    )

    assert _read(drawn) == (2, [(Fraction(3), {1})])


@pytest.mark.unit
def test_a_boundary_drawn_to_where_nothing_follows_leaves_no_fragment() -> None:
    assert (
        collapse(layout=_layout(fragments=_FOUR), inside=lambda ref: ref in (1, 2, 3), to=_at(4))
        is None
    )


@pytest.mark.unit
def test_the_end_of_the_last_fragment_drawn_to_the_end_of_the_score_opens_it() -> None:
    drawn: Layout[Fraction] | None = collapse(
        layout=_layout(fragments=_FOUR), inside=lambda ref: ref == 3, to=_at(4)
    )

    assert _read(drawn) == (1, [(Fraction(2), {1, 3}), (Fraction(4), {2})])


@pytest.mark.unit
def test_a_body_left_with_no_length_leaves_no_volta() -> None:
    assert collapse(layout=_layout(fragments=_FOUR), inside=lambda ref: ref == 0, to=_at(1)) is None


@pytest.mark.unit
def test_no_boundary_inside_leaves_the_layout_as_it_is() -> None:
    layout: Layout[Fraction] = _layout(fragments=_FOUR)

    assert _read(collapse(layout=layout, inside=lambda ref: False, to=_at(9))) == _read(layout)


@pytest.mark.unit
def test_a_pass_named_by_a_fragment_is_taken_from_the_one_that_had_it() -> None:
    layout: Layout[Fraction] = _layout(fragments=[(2, {1}), (3, {2, 3}), (4, {4})])

    moved: Layout[Fraction] = set_passes(layout=layout, index=2, passes=frozenset({3, 4}))

    assert _read(moved) == (1, [(Fraction(2), {1}), (Fraction(3), {2}), (Fraction(4), {3, 4})])
