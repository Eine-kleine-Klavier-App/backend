from fractions import Fraction

from piano_app.application.ports.importing import SourceClef, SourcePitch, SourceTime
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)

# Written note values the score has; a longer or a shorter one (breve, 64th) is not imported.
NOTE_TYPES: dict[str, RhythmicValue] = {
    "whole": RhythmicValue.WHOLE,
    "half": RhythmicValue.HALF,
    "quarter": RhythmicValue.QUARTER,
    "eighth": RhythmicValue.EIGHTH,
    "16th": RhythmicValue.SIXTEENTH,
    "32nd": RhythmicValue.THIRTY_SECOND,
}

BEAT_TYPES: dict[int, RhythmicValue] = {
    1: RhythmicValue.WHOLE,
    2: RhythmicValue.HALF,
    4: RhythmicValue.QUARTER,
    8: RhythmicValue.EIGHTH,
    16: RhythmicValue.SIXTEENTH,
    32: RhythmicValue.THIRTY_SECOND,
}

_ACCIDENTALS: dict[int, Accidental] = {
    -2: Accidental.DOUBLE_FLAT,
    -1: Accidental.FLAT,
    0: Accidental.NATURAL,
    1: Accidental.SHARP,
    2: Accidental.DOUBLE_SHARP,
}

_SEMITONES: dict[str, int] = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# The steps C D E F G A B are numbered 0 to 6. Sharps are added in the order F C G D A E B, flats
# in the order B E A D G C F.
_SHARP_ORDER: tuple[int, ...] = (3, 0, 4, 1, 5, 2, 6)
_FLAT_ORDER: tuple[int, ...] = (6, 2, 5, 1, 4, 0, 3)

_QUARTERS_PER_WHOLE: int = 4


def midi_of(*, pitch: SourcePitch) -> int:
    """The sounding pitch of a written one, as a MIDI note number."""
    return 12 * (pitch.octave + 1) + _SEMITONES[pitch.step] + pitch.alter


def accidental_of(*, pitch: SourcePitch) -> Accidental | None:
    """``None`` for an alteration the score has no sign for."""
    return _ACCIDENTALS.get(pitch.alter)


def alterations_of(*, fifths: int) -> tuple[Accidental, ...] | None:
    """The accidental of each step C to B in a key of ``fifths`` sharps (positive) or flats
    (negative); ``None`` beyond seven."""
    if abs(fifths) > len(_SHARP_ORDER):
        return None

    alterations: list[Accidental] = [Accidental.NATURAL] * len(_SHARP_ORDER)
    order: tuple[int, ...] = _SHARP_ORDER if fifths > 0 else _FLAT_ORDER
    sign: Accidental = Accidental.SHARP if fifths > 0 else Accidental.FLAT
    for step in order[: abs(fifths)]:
        alterations[step] = sign

    return tuple(alterations)


def clef_of(*, clef: SourceClef) -> tuple[Clef, int] | None:
    """The clef and its octave transposition; ``None`` for a clef the score has not got."""
    if clef.sign == "G" and clef.line in (2, None):
        return Clef.TREBLE, clef.octave_change

    if clef.sign == "F" and clef.line in (4, None):
        return Clef.BASS, clef.octave_change

    return None


def time_signature_of(*, time: SourceTime) -> RhythmicSize | None:
    """``None`` for a beat the score cannot count in (a 64th)."""
    beat: RhythmicValue | None = BEAT_TYPES.get(time.beat_type)
    if beat is None:
        return None

    return RhythmicSize(value=DottedRhythmicValue(value=beat), count=time.beats)


def size_of_length(*, quarters: Fraction) -> RhythmicSize | None:
    """The shortest way to count ``quarters`` quarter notes in equal steps of one note value:
    one quarter is 1/4, three eighths are 3/8. ``None`` for a length that is not whole steps
    of the finest value."""
    whole_notes: Fraction = quarters / _QUARTERS_PER_WHOLE
    for value in sorted(RhythmicValue):
        count: Fraction = whole_notes / value.fraction
        if count.denominator == 1 and count >= 1:
            return RhythmicSize(value=DottedRhythmicValue(value=value), count=int(count))

    return None
