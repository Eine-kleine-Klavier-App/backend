from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    RhythmicSize,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent

# A tuplet is never created empty: it comes with its first element, at its start, in the
# same gesture. ``written_size`` is the tuplet's interior (three eighths for a triplet of
# eighths), ``occupied_size`` what it takes where it lands (two eighths); the first
# element's ``written_value`` is read in the tuplet's own units.


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTupletWithNoteIntent(EditIntent):
    voice_id: str
    staff_id: str
    measure_id: str
    position: MeasurePosition
    written_size: RhythmicSize
    occupied_size: RhythmicSize
    written_value: DottedRhythmicValue
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTupletWithRestIntent(EditIntent):
    voice_id: str
    staff_id: str
    measure_id: str
    position: MeasurePosition
    written_size: RhythmicSize
    occupied_size: RhythmicSize
    written_value: DottedRhythmicValue
