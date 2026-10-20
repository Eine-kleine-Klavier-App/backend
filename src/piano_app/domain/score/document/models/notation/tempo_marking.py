from enum import StrEnum
from fractions import Fraction


class TempoMarking(StrEnum):
    GRAVE = "grave"
    LARGO = "largo"
    ADAGIO = "adagio"
    ANDANTE = "andante"
    MODERATO = "moderato"
    ALLEGRO = "allegro"
    PRESTO = "presto"

    @classmethod
    def for_bpm(cls, *, quarter_bpm: Fraction) -> TempoMarking:
        """Classify a tempo expressed in quarter notes per minute."""
        for upper, marking in _RANGE_ENDS:
            if quarter_bpm < upper:
                return marking
        return cls.PRESTO

    @property
    def typical_bpm(self) -> int:
        """Quarter notes per minute: the middle of the usual range of the word."""
        return _TYPICAL_BPM[self]


# the middle of the usual metronome range of each word, in quarter notes per minute
_TYPICAL_BPM: dict[TempoMarking, int] = {
    TempoMarking.GRAVE: 30,  # 20-40
    TempoMarking.LARGO: 50,  # 40-60
    TempoMarking.ADAGIO: 71,  # 66-76
    TempoMarking.ANDANTE: 92,  # 76-108
    TempoMarking.MODERATO: 114,  # 108-120
    TempoMarking.ALLEGRO: 138,  # 120-156
    TempoMarking.PRESTO: 184,  # 168-200
}


_RANGE_ENDS: tuple[tuple[int, TempoMarking], ...] = (
    (40, TempoMarking.GRAVE),
    (63, TempoMarking.LARGO),
    (76, TempoMarking.ADAGIO),
    (108, TempoMarking.ANDANTE),
    (120, TempoMarking.MODERATO),
    (162, TempoMarking.ALLEGRO),
)
