import pytest

from piano_app.domain.score.document.services.pitch import PitchTransform


@pytest.mark.parametrize("octave", [-4, -1, 0, 1, 5, 12])
@pytest.mark.parametrize(
    ("step", "semitones"), [(0, 0), (1, 2), (2, 4), (3, 5), (4, 7), (5, 9), (6, 11)]
)
def test_every_degree_across_octaves(octave: int, step: int, semitones: int) -> None:
    assert (
        PitchTransform(diatonic_origin=7 * octave).resolve(staff_step=step, accidental=0).midi_note
        == 12 * octave + semitones
    )


@pytest.mark.parametrize("step", range(-15, 16))
def test_seven_steps_advance_exactly_one_octave(step: int) -> None:
    transform = PitchTransform(diatonic_origin=25)
    lower = transform.resolve(staff_step=step, accidental=-1)
    upper = transform.resolve(staff_step=step + 7, accidental=-1)
    assert upper.midi_note - lower.midi_note == 12


@pytest.mark.parametrize("shift", [-20, -3, 0, 3, 20])
def test_opposite_octave_shifts_cancel_without_clamping(shift: int) -> None:
    transform = PitchTransform(diatonic_origin=37, octaves=shift)
    assert transform.resolve(staff_step=0, accidental=0, octaves=-shift).midi_note == 64
    assert transform.resolve(staff_step=0, accidental=0).midi_note == 64 + 12 * shift


@pytest.mark.parametrize(
    ("origin", "step", "expected"),
    [
        (0, -8, -13),
        (0, -7, -12),
        (0, -1, -1),
        (0, 0, 0),
        (0, 1, 2),
        (0, 2, 4),
        (0, 3, 5),
        (0, 4, 7),
        (0, 5, 9),
        (0, 6, 11),
        (0, 7, 12),
        (37, -2, 60),
        (37, 0, 64),
        (37, 3, 69),
        (25, 0, 43),
        (25, 10, 60),
    ],
)
def test_numeric_diatonic_positions(origin: int, step: int, expected: int) -> None:
    assert (
        PitchTransform(diatonic_origin=origin).resolve(staff_step=step, accidental=0).midi_note
        == expected
    )


@pytest.mark.parametrize("accidental", [-1, 0, 1])
@pytest.mark.parametrize("origin_octaves", [-2, -1, 0, 1, 2])
@pytest.mark.parametrize("range_octaves", [-2, -1, 0, 1, 2])
def test_all_shifts_contribute_to_final_pitch(
    accidental: int, origin_octaves: int, range_octaves: int
) -> None:
    pitch = PitchTransform(diatonic_origin=37, octaves=origin_octaves).resolve(
        staff_step=3, accidental=accidental, octaves=range_octaves
    )
    assert pitch.midi_note == 69 + accidental + 12 * (origin_octaves + range_octaves)


@pytest.mark.parametrize(
    ("step", "accidental", "expected"), [(6, 1, 12), (0, -1, -1), (6, 2, 13), (0, -2, -2)]
)
def test_accidental_can_cross_an_octave(step: int, accidental: int, expected: int) -> None:
    assert (
        PitchTransform(diatonic_origin=0).resolve(staff_step=step, accidental=accidental).midi_note
        == expected
    )
