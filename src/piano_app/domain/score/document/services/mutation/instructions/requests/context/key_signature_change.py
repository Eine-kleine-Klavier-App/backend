from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import NO_ACCIDENTALS, KeySignatureChange
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateKeySignatureChangeRequest(CreateMutationRequest[KeySignatureChange]):
    """A request to assert a key signature on one staff, starting at a measure
    position."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = KeySignatureChange

    measure: Measure
    position: MeasurePosition
    staff: Staff
    alterations: tuple[Accidental, ...] = NO_ACCIDENTALS
