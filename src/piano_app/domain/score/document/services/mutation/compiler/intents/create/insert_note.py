from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class InsertNoteIntent(EditIntent):
    voice_id: str
    staff_id: str
    measure_id: str
    position: MeasurePosition
    written_value: DottedRhythmicValue
    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE
