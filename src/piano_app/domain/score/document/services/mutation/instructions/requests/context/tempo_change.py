from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import TempoChange
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTempoChangeRequest(CreateMutationRequest[TempoChange]):
    """A request to assert a tempo for the score, starting at a measure position."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = TempoChange

    measure: Measure
    position: MeasurePosition
    beat: DottedRhythmicValue
    bpm: int
    show_label: bool = False
