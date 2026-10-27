from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateOctaveTranspositionRequest(CreateMutationRequest[OctaveTransposition]):
    """A request to assert an octave transposition on one staff, over a span."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = OctaveTransposition

    start_measure: Measure
    start_position: MeasurePosition
    end_measure: Measure
    end_position: MeasurePosition
    staff: Staff
    octaves: int
