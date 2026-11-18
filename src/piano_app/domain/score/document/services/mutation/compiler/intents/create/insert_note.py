from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent

# how much of a measure a beam entered by the editor holds before the next note begins another
DEFAULT_BEAM_SHARE: Fraction = Fraction(1, 2)


@dataclass(frozen=True, slots=True, kw_only=True)
class InsertNoteIntent(EditIntent):
    voice_id: str
    staff_id: str
    measure_id: str
    position: MeasurePosition
    written_value: DottedRhythmicValue
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE
    beam_share: Fraction = DEFAULT_BEAM_SHARE
