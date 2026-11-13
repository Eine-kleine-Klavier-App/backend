from dataclasses import dataclass, field
from fractions import Fraction
from itertools import permutations

import pytest

from piano_app.domain.score.document.services.geometry import (
    Frame,
    OutsideFrameError,
    Point,
    Span,
    Transform,
    UnreachableFrameError,
)
from piano_app.domain.score.document.services.pitch import (
    OctaveRegion,
    PitchRegion,
    PitchResolutionError,
    PitchResolver,
    PitchTransform,
)


@dataclass(frozen=True, kw_only=True)
class NumericFrame:
    extent: Fraction = Fraction(8)
    parent: Frame | None = None
    to_parent: Transform = field(default_factory=Transform.identity)
    identity: int = 0


def rule(frame: Frame, start: int, end: int, origin: int = 37) -> PitchRegion:
    return PitchRegion(
        span=Span(frame=frame, start=Fraction(start), length=Fraction(end - start)),
        transform=PitchTransform(diatonic_origin=origin),
    )


@pytest.mark.parametrize(
    ("position", "expected"),
    [(0, 65), (1, 65), (2, 77), (3, 77), (4, 56), (5, 56), (6, 44), (7, 44)],
)
def test_rule_and_octave_boundaries(position: int, expected: int) -> None:
    frame = NumericFrame()
    resolver = PitchResolver(
        frame=frame,
        regions=[rule(frame, 4, 8, 25), rule(frame, 0, 4)],
        octave_regions=[
            OctaveRegion(span=Span(frame=frame, start=Fraction(2), length=Fraction(4)), octaves=1)
        ],
    )
    assert (
        resolver.resolve(
            point=Point(frame=frame, value=Fraction(position)), staff_step=0, accidental=1
        ).midi_note
        == expected
    )


@pytest.mark.parametrize(("position", "octaves"), [(0, 0), (1, 1), (2, -1), (3, -1), (4, 0)])
def test_additive_ranges_and_touching_boundaries(position: int, octaves: int) -> None:
    frame = NumericFrame()
    resolver = PitchResolver(
        frame=frame,
        regions=[
            PitchRegion(
                span=Span(frame=frame, start=Fraction(0), length=Fraction(8)),
                transform=PitchTransform(diatonic_origin=37, octaves=1),
            )
        ],
        octave_regions=[
            OctaveRegion(span=Span(frame=frame, start=Fraction(1), length=Fraction(2)), octaves=1),
            OctaveRegion(span=Span(frame=frame, start=Fraction(2), length=Fraction(1)), octaves=-2),
            OctaveRegion(span=Span(frame=frame, start=Fraction(3), length=Fraction(1)), octaves=-1),
        ],
    )
    assert (
        resolver.resolve(
            point=Point(frame=frame, value=Fraction(position)), staff_step=0, accidental=0
        ).midi_note
        == 76 + 12 * octaves
    )


@pytest.mark.parametrize("position", [-1, 0, 2, 3, 8, 9])
def test_missing_rule_is_an_error(position: int) -> None:
    frame = NumericFrame()
    resolver = PitchResolver(frame=frame, regions=[rule(frame, 1, 2), rule(frame, 4, 8)])
    with pytest.raises(PitchResolutionError):
        resolver.resolve(
            point=Point(frame=frame, value=Fraction(position)), staff_step=0, accidental=0
        )


def test_empty_rules_have_no_implicit_default() -> None:
    frame = NumericFrame()
    with pytest.raises(PitchResolutionError, match="No pitch rule"):
        PitchResolver(frame=frame, regions=[]).resolve(
            point=Point(frame=frame, value=Fraction(0)), staff_step=0, accidental=0
        )


def test_overlapping_rules_are_ambiguous() -> None:
    frame = NumericFrame()
    with pytest.raises(PitchResolutionError, match="overlap"):
        PitchResolver(frame=frame, regions=[rule(frame, 0, 5), rule(frame, 4, 8)])


@pytest.mark.parametrize(("start", "end"), [(-1, 2), (0, 9)])
def test_region_must_fit_the_frame(start: int, end: int) -> None:
    frame = NumericFrame()
    with pytest.raises(PitchResolutionError, match="outside"):
        PitchResolver(frame=frame, regions=[rule(frame, start, end)])


def test_points_and_regions_can_be_in_related_frames() -> None:
    root = NumericFrame()
    local = NumericFrame(
        parent=root,
        extent=Fraction(2),
        to_parent=Transform(scale=Fraction(2), offset=Fraction(2)),
    )
    resolver = PitchResolver(frame=root, regions=[rule(local, 0, 2)])
    assert (
        resolver.resolve(
            point=Point(frame=local, value=Fraction(1)), staff_step=3, accidental=0
        ).midi_note
        == 69
    )


def test_foreign_coordinates_are_refused() -> None:
    root = NumericFrame()
    foreign = NumericFrame(identity=1)
    resolver = PitchResolver(frame=root, regions=[rule(root, 0, 8)])
    with pytest.raises(UnreachableFrameError):
        resolver.resolve(point=Point(frame=foreign, value=Fraction(1)), staff_step=0, accidental=0)
    with pytest.raises(UnreachableFrameError):
        PitchResolver(frame=root, regions=[rule(foreign, 0, 8)])


@pytest.mark.parametrize("boundary", [Fraction(1, 3), Fraction(2, 3)])
@pytest.mark.parametrize("offset", [Fraction(-1, 10000), Fraction(0), Fraction(1, 10000)])
def test_fractional_boundaries(boundary: Fraction, offset: Fraction) -> None:
    frame = NumericFrame(extent=Fraction(1))
    split = Fraction(1, 3)
    resolver = PitchResolver(
        frame=frame,
        regions=[
            PitchRegion(
                span=Span(frame=frame, start=Fraction(0), length=split),
                transform=PitchTransform(diatonic_origin=37),
            ),
            PitchRegion(
                span=Span(frame=frame, start=split, length=1 - split),
                transform=PitchTransform(diatonic_origin=25),
            ),
        ],
        octave_regions=[OctaveRegion(span=Span(frame=frame, start=split, length=split), octaves=1)],
    )
    at = boundary + offset
    expected = 64 if at < split else (55 if at < 2 * split else 43)
    assert (
        resolver.resolve(point=Point(frame=frame, value=at), staff_step=0, accidental=0).midi_note
        == expected
    )


def test_nested_coincident_shifts_are_order_independent() -> None:
    frame = NumericFrame()
    shifts = [
        OctaveRegion(span=Span(frame=frame, start=Fraction(1), length=Fraction(6)), octaves=1),
        OctaveRegion(span=Span(frame=frame, start=Fraction(2), length=Fraction(2)), octaves=2),
        OctaveRegion(span=Span(frame=frame, start=Fraction(2), length=Fraction(2)), octaves=-1),
    ]
    regions = [rule(frame, 0, 4), rule(frame, 4, 8, 25)]
    for ordered_rules in permutations(regions):
        for ordered_shifts in permutations(shifts):
            resolver = PitchResolver(
                frame=frame, regions=ordered_rules, octave_regions=ordered_shifts
            )
            for at, expected in [(0, 64), (1, 76), (2, 88), (3, 88), (4, 55), (7, 43)]:
                assert (
                    resolver.resolve(
                        point=Point(frame=frame, value=Fraction(at)), staff_step=0, accidental=0
                    ).midi_note
                    == expected
                )


def test_opposite_coincident_ranges_cancel() -> None:
    frame = NumericFrame()
    span = Span(frame=frame, start=Fraction(1), length=Fraction(2))
    resolver = PitchResolver(
        frame=frame,
        regions=[rule(frame, 0, 8)],
        octave_regions=[OctaveRegion(span=span, octaves=2), OctaveRegion(span=span, octaves=-2)],
    )
    for at in (0, 1, 2, 3):
        assert (
            resolver.resolve(
                point=Point(frame=frame, value=Fraction(at)), staff_step=0, accidental=0
            ).midi_note
            == 64
        )


def test_octave_ranges_are_converted_from_local_frames() -> None:
    root = NumericFrame()
    local = NumericFrame(
        parent=root, extent=Fraction(2), to_parent=Transform(scale=Fraction(2), offset=Fraction(2))
    )
    resolver = PitchResolver(
        frame=root,
        regions=[rule(root, 0, 8)],
        octave_regions=[
            OctaveRegion(span=Span(frame=local, start=Fraction(0), length=Fraction(1)), octaves=1)
        ],
    )
    for at, expected in [(1, 64), (2, 76), (3, 76), (4, 64)]:
        assert (
            resolver.resolve(
                point=Point(frame=root, value=Fraction(at)), staff_step=0, accidental=0
            ).midi_note
            == expected
        )


@pytest.mark.parametrize("foreign", [False, True])
def test_invalid_octave_region_coordinates(foreign: bool) -> None:
    root = NumericFrame()
    frame = NumericFrame(identity=1) if foreign else root
    with pytest.raises(UnreachableFrameError if foreign else PitchResolutionError):
        PitchResolver(
            frame=root,
            regions=[rule(root, 0, 8)],
            octave_regions=[
                OctaveRegion(
                    span=Span(frame=frame, start=Fraction(7), length=Fraction(2)), octaves=1
                )
            ],
        )


def test_conversion_outside_target_frame_fails() -> None:
    root = NumericFrame()
    local = NumericFrame(
        parent=root, extent=Fraction(2), to_parent=Transform.of_shift(offset=Fraction(7))
    )
    resolver = PitchResolver(frame=root, regions=[rule(root, 0, 8)])
    with pytest.raises(OutsideFrameError):
        resolver.resolve(point=Point(frame=local, value=Fraction(2)), staff_step=0, accidental=0)
    with pytest.raises(OutsideFrameError):
        PitchResolver(frame=root, regions=[rule(local, 0, 2)])


def test_input_lists_are_snapshotted() -> None:
    frame = NumericFrame()
    regions = [rule(frame, 0, 8)]
    shifts = [
        OctaveRegion(span=Span(frame=frame, start=Fraction(1), length=Fraction(2)), octaves=1)
    ]
    resolver = PitchResolver(frame=frame, regions=regions, octave_regions=shifts)
    regions[:] = [rule(frame, 0, 8, 25)]
    shifts.clear()
    assert (
        resolver.resolve(
            point=Point(frame=frame, value=Fraction(1)), staff_step=0, accidental=0
        ).midi_note
        == 76
    )
