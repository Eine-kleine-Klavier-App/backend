from dataclasses import dataclass, field
from fractions import Fraction
from itertools import product

import pytest

from piano_app.domain.score.document.models.context import ClefChange, OctaveTransposition
from piano_app.domain.score.document.models.notation import Accidental, Clef
from piano_app.domain.score.document.services.geometry import Frame, Point, Span, Transform
from piano_app.domain.score.document.services.pitch import (
    OctaveRegion,
    PitchRegion,
    PitchResolutionError,
    PitchResolver,
    PitchTransform,
)

from .test_score_pitch import PitchScene, build_scene

# The inverse of resolving: the staff step that sounds a given pitch, written with a given
# accidental, under a clef and the octave lines over it.

_TREBLE: int = 37
_BASS: int = 25


@pytest.mark.parametrize("origin", [_TREBLE, _BASS, 0, 3, 40, -4])
@pytest.mark.parametrize("octaves", [-2, 0, 1])
@pytest.mark.parametrize("extra", [-1, 0, 2])
@pytest.mark.parametrize("accidental", [-1, 0, 1])
def test_the_inverse_gives_back_every_step(
    origin: int, octaves: int, extra: int, accidental: int
) -> None:
    transform = PitchTransform(diatonic_origin=origin, octaves=octaves)
    for staff_step in range(-25, 30):
        midi_note: int = transform.resolve(
            staff_step=staff_step, accidental=accidental, octaves=extra
        ).midi_note

        assert (
            transform.staff_step_for(midi_note=midi_note, accidental=accidental, octaves=extra)
            == staff_step
        )


@pytest.mark.parametrize(("staff_step", "accidental"), list(product(range(-14, 15), (-1, 0, 1))))
def test_a_pitch_written_in_one_clef_can_be_written_in_the_other(
    staff_step: int, accidental: int
) -> None:
    treble = PitchTransform(diatonic_origin=_TREBLE)
    bass = PitchTransform(diatonic_origin=_BASS)
    midi_note: int = treble.resolve(staff_step=staff_step, accidental=accidental).midi_note

    other: int = bass.staff_step_for(midi_note=midi_note, accidental=accidental)

    assert bass.resolve(staff_step=other, accidental=accidental).midi_note == midi_note
    # the same letter, so a whole number of octaves apart in steps
    assert (other - staff_step - (_TREBLE - _BASS)) % 7 == 0


@pytest.mark.parametrize("midi_note", [61, 63, 66, 68, 70])
def test_a_black_key_cannot_be_written_with_a_natural(midi_note: int) -> None:
    with pytest.raises(ValueError, match="cannot be written with this accidental"):
        PitchTransform(diatonic_origin=_TREBLE).staff_step_for(midi_note=midi_note, accidental=0)


@pytest.mark.parametrize(
    ("midi_note", "accidental"),
    [
        (61, 1),
        (63, -1),
        (66, 1),
        (68, -1),
        (70, 1),
        (60, 0),
        (65, 0),
        (62, 2),
        (61, 2),
        (58, -2),
        (62, -2),
    ],
)
def test_a_pitch_is_written_with_the_accidental_that_leaves_a_white_key(
    midi_note: int, accidental: int
) -> None:
    transform = PitchTransform(diatonic_origin=_TREBLE)

    staff_step: int = transform.staff_step_for(midi_note=midi_note, accidental=accidental)

    assert transform.resolve(staff_step=staff_step, accidental=accidental).midi_note == midi_note


@pytest.mark.parametrize(
    ("midi_note", "accidental"), [(62, 1), (67, 1), (60, -1), (65, -1), (60, 2), (61, -2)]
)
def test_an_accidental_over_a_black_key_is_a_pitch_no_step_can_hold(
    midi_note: int, accidental: int
) -> None:
    """Taking the accidental off leaves a black key, which no step holds."""
    with pytest.raises(ValueError, match="cannot be written with this accidental"):
        PitchTransform(diatonic_origin=_TREBLE).staff_step_for(
            midi_note=midi_note, accidental=accidental
        )


@dataclass(frozen=True, kw_only=True)
class NumericFrame:
    extent: Fraction = Fraction(8)
    parent: Frame | None = None
    to_parent: Transform = field(default_factory=Transform.identity)
    identity: int = 0


def _rule(frame: Frame, start: int, end: int, origin: int) -> PitchRegion:
    return PitchRegion(
        span=Span(frame=frame, start=Fraction(start), length=Fraction(end - start)),
        transform=PitchTransform(diatonic_origin=origin),
    )


@pytest.mark.parametrize("position", range(8))
def test_the_resolver_inverts_through_the_rule_and_the_octave_lines_at_each_point(
    position: int,
) -> None:
    frame = NumericFrame()
    resolver = PitchResolver(
        frame=frame,
        regions=[_rule(frame, 0, 4, _TREBLE), _rule(frame, 4, 8, _BASS)],
        octave_regions=[
            OctaveRegion(span=Span(frame=frame, start=Fraction(2), length=Fraction(4)), octaves=1)
        ],
    )
    point = Point(frame=frame, value=Fraction(position))

    for staff_step, accidental in product(range(-9, 12), (-1, 0, 1)):
        midi_note: int = resolver.resolve(
            point=point, staff_step=staff_step, accidental=accidental
        ).midi_note

        assert (
            resolver.staff_step_for(point=point, midi_note=midi_note, accidental=accidental)
            == staff_step
        )


def test_the_resolver_refuses_the_inverse_where_it_has_no_rule() -> None:
    frame = NumericFrame()
    resolver = PitchResolver(frame=frame, regions=[_rule(frame, 0, 4, _TREBLE)])

    with pytest.raises(PitchResolutionError, match="No pitch rule"):
        resolver.staff_step_for(
            point=Point(frame=frame, value=Fraction(5)), midi_note=60, accidental=0
        )

    with pytest.raises(PitchResolutionError, match="outside the timeline"):
        resolver.staff_step_for(
            point=Point(frame=frame, value=Fraction(9)), midi_note=60, accidental=0
        )


def test_the_index_inverts_under_a_clef_change_and_an_octave_line() -> None:
    scene: PitchScene = build_scene()
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    OctaveTransposition.create(
        start=scene.anchor(Fraction(2)), end=scene.anchor(Fraction(3)), staff=scene.upper, octaves=1
    )
    scene.pitch.invalidate_measures()

    for at, staff_step, accidental in product(
        (Fraction(0), Fraction(1), Fraction(5, 2), Fraction(7, 2)),
        range(-7, 8),
        (Accidental.FLAT, Accidental.NATURAL, Accidental.SHARP),
    ):
        pitch = scene.resolve(at, step=staff_step, accidental=accidental)

        assert (
            scene.pitch.staff_step_for(
                staff=scene.upper,
                point=Point(frame=scene.geometry.root, value=at),
                midi_note=pitch.midi_note,
                accidental=accidental,
            )
            == staff_step
        )


def test_the_index_inverts_a_pitch_into_the_other_staff_and_clef() -> None:
    scene: PitchScene = build_scene()
    point = Point(frame=scene.geometry.root, value=Fraction(1, 2))
    written = scene.resolve(Fraction(1, 2), staff=scene.upper, step=0)

    lower_step: int = scene.pitch.staff_step_for(
        staff=scene.lower, point=point, midi_note=written.midi_note, accidental=Accidental.NATURAL
    )

    assert scene.resolve(Fraction(1, 2), staff=scene.lower, step=lower_step) == written
    assert lower_step == 12


def test_the_index_refuses_the_inverse_for_a_staff_of_another_document() -> None:
    scene: PitchScene = build_scene()
    other: PitchScene = build_scene()

    with pytest.raises(ValueError, match="not in the pitch index's document"):
        scene.pitch.staff_step_for(
            staff=other.upper,
            point=Point(frame=scene.geometry.root, value=Fraction(0)),
            midi_note=60,
            accidental=Accidental.NATURAL,
        )


def test_the_index_inverts_nothing_before_its_first_clef() -> None:
    scene: PitchScene = build_scene()
    scene.document.measures[0].anchors[0].starting_contexts[0].detach()
    scene.pitch.invalidate_staff(staff=scene.upper)

    with pytest.raises(PitchResolutionError):
        scene.pitch.staff_step_for(
            staff=scene.upper,
            point=Point(frame=scene.geometry.root, value=Fraction(0)),
            midi_note=60,
            accidental=Accidental.NATURAL,
        )
