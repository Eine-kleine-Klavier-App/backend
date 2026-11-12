from fractions import Fraction

import pytest

from piano_app.domain.score.document.services.geometry import (
    Duration,
    FrameMismatchError,
    OutsideFrameError,
    Point,
    Span,
    Transform,
    UnreachableFrameError,
)

from .conftest import StubFrame


@pytest.mark.unit
def test_a_point_lands_where_the_nesting_puts_it(root: StubFrame, triplet: StubFrame) -> None:
    assert Point(frame=triplet, value=Fraction(0)).to(frame=root).value == Fraction(1, 4)
    assert Point(frame=triplet, value=Fraction(1, 8)).to(frame=root).value == Fraction(1, 3)
    assert Point(frame=triplet, value=Fraction(3, 8)).to(frame=root).value == Fraction(1, 2)


@pytest.mark.unit
def test_a_duration_needs_neither_an_offset_nor_a_home(
    root: StubFrame,
    triplet: StubFrame,
) -> None:
    """A length is a displacement, so restating it asks only about the squeeze — which
    is why it also needs no containment check."""
    written_eighth: Duration = Duration(frame=triplet, value=Fraction(1, 8))

    assert written_eighth.to(frame=root).value == Fraction(1, 12)


@pytest.mark.unit
def test_cousins_convert_without_a_common_ancestor_walk(
    root: StubFrame,
    triplet: StubFrame,
) -> None:
    """Two frames hanging off the same root convert straight across — here the
    tuplet's own coordinates into the measure that holds it."""
    first_measure: StubFrame = StubFrame(
        name="measure0",
        parent=root,
        to_parent=Transform.of_shift(offset=Fraction(0)),
        extent=Fraction(1),
    )
    inside_triplet: Point = Point(frame=triplet, value=Fraction(1, 8))

    in_measure: Point = inside_triplet.to(frame=first_measure)

    assert in_measure.value == Fraction(1, 3)
    assert in_measure.to(frame=triplet).value == Fraction(1, 8)


@pytest.mark.unit
def test_a_point_in_a_measure_that_does_not_hold_it_is_refused(
    measure: StubFrame,
    triplet: StubFrame,
) -> None:
    """The triplet sits in the first measure, so asking for its coordinates in the
    second has no answer."""
    with pytest.raises(OutsideFrameError):
        Point(frame=triplet, value=Fraction(1, 8)).to(frame=measure)


@pytest.mark.unit
def test_a_round_trip_through_the_root_is_exact(root: StubFrame, triplet: StubFrame) -> None:
    deeper: StubFrame = StubFrame(
        name="inner",
        parent=triplet,
        to_parent=Transform.of_nesting(
            written=Fraction(1, 4), occupied=Fraction(1, 8), offset=Fraction(1, 8)
        ),
        extent=Fraction(1, 4),
    )
    original: Point = Point(frame=deeper, value=Fraction(1, 7))

    assert original.to(frame=root).to(frame=deeper).value == Fraction(1, 7)


@pytest.mark.unit
def test_climbing_to_the_root_refuses_only_past_the_timelines_end(
    root: StubFrame,
    triplet: StubFrame,
    measure: StubFrame,
) -> None:
    """Outgrowing a group is fine on the way up — the timeline holds it; a point past the
    timeline's own end has no coordinate there."""
    outgrowing: Span = Span(frame=triplet, start=Fraction(1, 4), length=Fraction(1, 2))

    assert outgrowing.to(frame=root).start == Fraction(5, 12)
    with pytest.raises(OutsideFrameError):
        Point(frame=measure, value=Fraction(4)).to(frame=root)


@pytest.mark.unit
def test_a_point_outside_the_target_has_no_answer(root: StubFrame, measure: StubFrame) -> None:
    with pytest.raises(OutsideFrameError):
        Point(frame=root, value=Fraction(1, 2)).to(frame=measure)


@pytest.mark.unit
def test_a_span_that_does_not_fit_is_refused_rather_than_truncated(
    root: StubFrame,
    measure: StubFrame,
) -> None:
    """Forcing a crossing span into one frame is a nonsense request — ask what it
    meets instead."""
    crossing: Span = Span(frame=root, start=Fraction(7, 4), length=Fraction(1, 2))

    with pytest.raises(OutsideFrameError):
        crossing.to(frame=measure)


@pytest.mark.unit
def test_a_span_that_exactly_fills_its_frame_is_accepted(
    root: StubFrame,
    measure: StubFrame,
) -> None:
    """The end bound is inclusive: sitting on the closing barline is a real
    coordinate, not an overflow."""
    exact: Span = Span(frame=root, start=Fraction(1), length=Fraction(1))

    assert exact.to(frame=measure).end == Fraction(1)


@pytest.mark.unit
def test_frames_from_different_timelines_do_not_convert(root: StubFrame) -> None:
    elsewhere: StubFrame = StubFrame(
        name="another timeline",
        parent=None,
        to_parent=Transform.identity(),
        extent=Fraction(4),
    )

    with pytest.raises(UnreachableFrameError):
        Point(frame=root, value=Fraction(0)).to(frame=elsewhere)


@pytest.mark.unit
def test_frames_compare_by_what_they_stand_for_not_by_object(triplet: StubFrame) -> None:
    """Bridges over the live model are rebuilt constantly, so one space is many
    objects — comparing by identity would make coordinates incombinable."""
    same_space: StubFrame = StubFrame(
        name=triplet.name,
        parent=triplet.parent,
        to_parent=triplet.to_parent,
        extent=triplet.extent,
    )

    assert same_space is not triplet
    assert Span(frame=triplet, start=Fraction(0), length=Fraction(1, 8)).intersects(
        Span(frame=same_space, start=Fraction(0), length=Fraction(1, 8))
    )


@pytest.mark.unit
def test_combining_coordinates_of_different_frames_is_a_caller_bug(
    root: StubFrame,
    triplet: StubFrame,
) -> None:
    with pytest.raises(FrameMismatchError):
        Span(frame=root, start=Fraction(0), length=Fraction(1)).intersects(
            Span(frame=triplet, start=Fraction(0), length=Fraction(1, 8))
        )


@pytest.mark.unit
def test_touching_spans_do_not_overlap(root: StubFrame) -> None:
    """Half-open, so a note ending where the next begins is adjacency, not a clash."""
    first: Span = Span(frame=root, start=Fraction(0), length=Fraction(1, 4))
    second: Span = Span(frame=root, start=Fraction(1, 4), length=Fraction(1, 4))

    assert not first.intersects(second)
    assert first.intersection(second) is None


@pytest.mark.unit
def test_uncovered_parts_are_swept_left_to_right(root: StubFrame) -> None:
    bucket: Span = Span(frame=root, start=Fraction(0), length=Fraction(1))
    covered: list[Span] = [
        Span(frame=root, start=Fraction(1, 2), length=Fraction(1, 4)),
        Span(frame=root, start=Fraction(0), length=Fraction(1, 4)),
    ]

    assert bucket.remainder_after(covered) == [
        Span(frame=root, start=Fraction(1, 4), length=Fraction(1, 4)),
        Span(frame=root, start=Fraction(3, 4), length=Fraction(1, 4)),
    ]


@pytest.mark.unit
def test_overlapping_covers_do_not_confuse_the_sweep(root: StubFrame) -> None:
    """A cover ending before one already passed must not reopen a hole."""
    bucket: Span = Span(frame=root, start=Fraction(0), length=Fraction(1))
    covered: list[Span] = [
        Span(frame=root, start=Fraction(0), length=Fraction(3, 4)),
        Span(frame=root, start=Fraction(1, 4), length=Fraction(1, 4)),
    ]

    assert bucket.remainder_after(covered) == [
        Span(frame=root, start=Fraction(3, 4), length=Fraction(1, 4))
    ]


@pytest.mark.unit
def test_a_fully_covered_bucket_leaves_nothing(root: StubFrame) -> None:
    bucket: Span = Span(frame=root, start=Fraction(0), length=Fraction(1))

    assert bucket.remainder_after([bucket]) == []


@pytest.mark.unit
def test_a_span_needs_real_length(root: StubFrame) -> None:
    with pytest.raises(ValueError, match="length must be positive"):
        Span(frame=root, start=Fraction(0), length=Fraction(0))


@pytest.mark.unit
def test_a_duration_cannot_run_backwards(root: StubFrame) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        Duration(frame=root, value=Fraction(-1, 4))


@pytest.mark.unit
def test_two_points_make_the_length_between_them(root: StubFrame) -> None:
    start: Point = Point(frame=root, value=Fraction(1, 4))
    end: Point = Point(frame=root, value=Fraction(3, 4))

    assert start.distance_to(other=end) == Duration(frame=root, value=Fraction(1, 2))
    assert Span.between(start=start, end=end).length == Fraction(1, 2)
