from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeDurationIntent(EditIntent):
    """Give this note or rest carrier's element a new written value, from where it starts;
    the value is read in the units of the element's scope."""

    carrier_id: str
    written_value: DottedRhythmicValue
