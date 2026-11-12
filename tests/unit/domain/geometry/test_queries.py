from fractions import Fraction

import pytest

from piano_app.domain.score.document.services.geometry import (
    FrameMismatchError,
    Point,
    Span,
    Transform,
    containing,
    footprint,
    gaps,
    interior,
    meetings,
    overflow,
)

from .conftest import StubFrame


def _measure(*, root: StubFrame, index: int) -> StubFrame:
    return StubFrame(
        name=f"measure{index}",
        parent=root,
        to_parent=Transform.of_shift(offset=Fraction(index)),
        extent=Fraction(1),
    )


@pytest.mark.unit
def test_a_span_crossing_a_boundary_reports_its_pieces(root: StubFrame) -> None:
    """The whole point of the primitive: crossing is answered with data, so slicing
    or refusing stays the caller's decision."""
    measures = [_measure(root=root, index=index) for index in range(3)]
    crossing: Span = Span(frame=root, start=Fraction(3, 4), length=Fraction(1, 2))

    met = meetings(
        span=crossing,
        candidates=[(measure.name, footprint(frame=measure)) for measure in measures],
    )

    assert [(m.region, m.part.start, m.part.end) for m in met] == [
        ("measure0", Fraction(3, 4), Fraction(1)),
        ("measure1", Fraction(1), Fraction(5, 4)),
    ]


@pytest.mark.unit
def test_meetings_come_back_in_timeline_order(root: StubFrame) -> None:
    measures = [_measure(root=root, index=index) for index in range(3)]
    long_span: Span = Span(frame=root, start=Fraction(1, 2), length=Fraction(2))

    met = meetings(
        span=long_span,
        candidates=[(measure.name, footprint(frame=measure)) for measure in reversed(measures)],
    )

    assert [m.region for m in met] == ["measure0", "measure1", "measure2"]


@pytest.mark.unit
def test_a_span_inside_one_region_meets_only_it(root: StubFrame) -> None:
    measures = [_measure(root=root, index=index) for index in range(3)]
    contained: Span = Span(frame=root, start=Fraction(5, 4), length=Fraction(1, 8))

    met = meetings(span=contained, candidates=[(b.name, footprint(frame=b)) for b in measures])

    assert [m.region for m in met] == ["measure1"]


@pytest.mark.unit
def test_a_boundary_point_belongs_to_the_region_starting_there(root: StubFrame) -> None:
    """Half-open, kept consistent with Span so a position never lands twice."""
    measures = [_measure(root=root, index=index) for index in range(3)]
    candidates = [(measure.name, footprint(frame=measure)) for measure in measures]

    assert (
        containing(point=Point(frame=root, value=Fraction(1)), candidates=candidates) == "measure1"
    )


@pytest.mark.unit
def test_a_point_between_regions_belongs_to_none(root: StubFrame) -> None:
    """Reported as absence, not as an error — running off the end is something the
    caller answers for."""
    measures = [_measure(root=root, index=index) for index in range(2)]

    assert (
        containing(
            point=Point(frame=root, value=Fraction(99)),
            candidates=[(measure.name, footprint(frame=measure)) for measure in measures],
        )
        is None
    )


@pytest.mark.unit
def test_locating_a_point_among_regions_of_another_frame_is_a_bug(
    root: StubFrame,
    triplet: StubFrame,
) -> None:
    with pytest.raises(FrameMismatchError):
        containing(
            point=Point(frame=triplet, value=Fraction(0)),
            candidates=[("measure", footprint(frame=_measure(root=root, index=0)))],
        )


@pytest.mark.unit
def test_footprint_and_interior_are_the_same_room_seen_from_two_sides(
    triplet: StubFrame,
) -> None:
    """From outside a triplet takes a quarter; from inside it measures three
    eighths — the written/occupied duality, derived from one step."""
    assert footprint(frame=triplet).length == Fraction(1, 4)
    assert interior(frame=triplet).length == Fraction(3, 8)
    assert footprint(frame=triplet).start == Fraction(1, 4)
    assert interior(frame=triplet).start == Fraction(0)


@pytest.mark.unit
def test_a_measure_takes_up_exactly_its_own_length(root: StubFrame) -> None:
    """The degenerate case: nothing is compressed, so both faces agree."""
    measure: StubFrame = _measure(root=root, index=2)

    assert footprint(frame=measure).length == interior(frame=measure).length == Fraction(1)


@pytest.mark.unit
def test_the_root_takes_up_no_room_but_its_interior_is_the_whole_timeline(
    root: StubFrame,
) -> None:
    with pytest.raises(ValueError, match="no parent"):
        footprint(frame=root)

    assert interior(frame=root) == Span(frame=root, start=Fraction(0), length=Fraction(4))


@pytest.mark.unit
def test_outgrowing_a_frame_is_a_number_not_an_error(triplet: StubFrame) -> None:
    """What used to raise inside the geometry now comes back as a fact to weigh."""
    too_long: Span = Span(frame=triplet, start=Fraction(1, 4), length=Fraction(1, 2))

    assert overflow(span=too_long) == Fraction(3, 8)


@pytest.mark.unit
def test_a_span_that_fits_overflows_by_nothing(triplet: StubFrame) -> None:
    assert overflow(span=interior(frame=triplet)) == Fraction(0)


@pytest.mark.unit
def test_running_past_the_timelines_end_is_an_overflow(root: StubFrame) -> None:
    """The timeline is bounded like a group: what runs past its last measure outgrows it."""
    assert overflow(span=Span(frame=root, start=Fraction(3), length=Fraction(2))) == Fraction(1)


@pytest.mark.unit
def test_a_region_nobody_covers_reports_as_one_whole_hole(root: StubFrame) -> None:
    """Geometry does not decide that an untouched region is asleep — it reports the
    hole honestly and leaves the judgement to the filler."""
    bucket: Span = Span(frame=root, start=Fraction(1), length=Fraction(1))

    assert gaps(bucket=bucket, covered=[]) == [bucket]
