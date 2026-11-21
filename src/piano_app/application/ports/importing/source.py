from dataclasses import dataclass
from fractions import Fraction

from .issues import ImportIssue

# The score as a file states it, before anything of ours is built from it. Time is in quarter notes
# counted from the start of the measure the entry stands in; pitch and clef are as written, not yet
# resolved to a staff step.


@dataclass(frozen=True, slots=True, kw_only=True)
class SourcePitch:
    step: str
    """``"C"`` to ``"B"``."""

    alter: int
    """Semitones: -2 (double flat) to 2 (double sharp)."""

    octave: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceNote:
    onset: Fraction
    duration: Fraction
    """Sounding length; 0 for a grace note."""

    voice: int
    staff: int
    """1-based, within the part."""

    pitch: SourcePitch | None
    """``None`` for a rest."""

    written_type: str | None
    """``"quarter"``, ``"eighth"`` and so on; ``None`` for a rest that fills the measure."""

    dots: int
    tuplet: tuple[int, int] | None
    """``(actual, normal)``: three in the time of two is ``(3, 2)``."""

    is_chord_member: bool
    """Sounds at the onset of the note before it."""

    is_grace: bool
    is_slashed: bool
    """A grace note with a slash through its stem (an acciaccatura)."""

    is_measure_rest: bool
    tie_start: bool
    tie_stop: bool
    articulations: frozenset[str]
    """MusicXML names: ``"staccato"``, ``"accent"``, ``"fermata"``, ``"arpeggio-up"`` ..."""

    ornament: str | None
    """A MusicXML name: ``"trill-mark"``, ``"mordent"``, ``"tremolo-1"`` ..."""

    fingering: int | None

    beam: str | None = None
    """Where the note stands in the first beam of the file: ``"begin"``, ``"continue"`` or
    ``"end"``; ``None`` for a note that is not beamed. The further beams of the file are the notes'
    own shorter values and say nothing the notes do not."""

    stem: str | None = None
    """``"up"`` or ``"down"`` as the file draws the stem; ``None`` when it has none (a rest, a
    whole note) or the file says nothing of it."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceClef:
    staff: int
    onset: Fraction
    sign: str
    line: int | None
    octave_change: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceKey:
    onset: Fraction
    fifths: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceTime:
    beats: int
    beat_type: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceDynamic:
    onset: Fraction
    marking: str
    """``"p"``, ``"mf"``, ``"sfz"`` ..."""

    staff: int = 1
    """The staff the file puts it on (1-based); a direction with no staff is on the first."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceWedge:
    onset: Fraction
    kind: str
    """``"crescendo"``, ``"diminuendo"`` or ``"stop"``."""

    staff: int = 1
    """The staff the file puts it on (1-based); a direction with no staff is on the first."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceTempo:
    onset: Fraction
    bpm: int
    beat_type: str | None
    """The note value the tempo counts in (``"quarter"``); ``None`` when the file only gives beats
    per minute of a quarter."""

    dots: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourcePedal:
    onset: Fraction
    kind: str
    """``"start"``, ``"stop"``, ``"change"`` (a stop and a start) or ``"continue"``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOctaveShift:
    onset: Fraction
    staff: int
    kind: str
    """``"up"``, ``"down"`` or ``"stop"``."""

    size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceSlur:
    onset: Fraction
    kind: str
    """``"start"`` or ``"stop"``."""

    number: int
    voice: int
    staff: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceBarline:
    """A repeat sign or an ending bracket at a barline of the measure."""

    location: str
    """``"left"`` or ``"right"``."""

    repeat: str | None
    """``"forward"`` or ``"backward"``."""

    times: int | None
    ending_number: str | None
    ending_kind: str | None
    """``"start"``, ``"stop"`` or ``"discontinue"``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceMeasure:
    number: str
    """As the file numbers it; not unique and not always a number."""

    index: int
    """0-based position in the file."""

    time: SourceTime
    """The time signature in force in this measure."""

    is_implicit: bool
    """The file marks it as a partial measure (a pickup)."""

    extent: Fraction
    """How far the notes of the measure reach, in quarter notes."""

    notes: tuple[SourceNote, ...]
    clefs: tuple[SourceClef, ...]
    keys: tuple[SourceKey, ...]
    dynamics: tuple[SourceDynamic, ...]
    wedges: tuple[SourceWedge, ...]
    tempos: tuple[SourceTempo, ...]
    pedals: tuple[SourcePedal, ...]
    octave_shifts: tuple[SourceOctaveShift, ...]
    slurs: tuple[SourceSlur, ...]
    barlines: tuple[SourceBarline, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceScore:
    title: str | None
    staff_count: int
    measures: tuple[SourceMeasure, ...]
    issues: tuple[ImportIssue, ...]
