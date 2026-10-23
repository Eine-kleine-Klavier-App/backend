from dataclasses import dataclass

from .values import Pitch

_SEMITONES: tuple[int, ...] = (0, 2, 4, 5, 7, 9, 11)


@dataclass(frozen=True, slots=True, kw_only=True)
class PitchTransform:
    """A numeric diatonic origin for staff step zero, plus an octave shift.

    Diatonic zero maps to MIDI zero. Seven diatonic steps advance twelve semitones;
    floor division keeps the same rule below zero. Accidentals are semitone offsets.
    """

    diatonic_origin: int
    octaves: int = 0

    def staff_step_for(self, *, midi_note: int, accidental: int, octaves: int = 0) -> int:
        """The staff step that resolves to ``midi_note`` under this transform with the
        accidental and the extra octave shift: the inverse of ``resolve``.

        Every white key sits on some step whichever the clef, so a pitch written with the
        same accidental stays writable; a note that is not a white key once the accidental
        is taken off is refused.
        """
        natural: int = midi_note - accidental - 12 * (self.octaves + octaves)
        octave, remainder = divmod(natural, 12)
        if remainder not in _SEMITONES:
            raise ValueError("This pitch cannot be written with this accidental.")

        return 7 * octave + _SEMITONES.index(remainder) - self.diatonic_origin

    def resolve(self, *, staff_step: int, accidental: int, octaves: int = 0) -> Pitch:
        octave, step = divmod(self.diatonic_origin + staff_step, 7)
        return Pitch(
            midi_note=12 * (octave + self.octaves + octaves) + _SEMITONES[step] + accidental
        )
