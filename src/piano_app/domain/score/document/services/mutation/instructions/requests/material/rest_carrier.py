from dataclasses import dataclass

from piano_app.domain.score.document.models.material import RestCarrier
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import RhythmicContainerParent
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
    DeleteMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRestCarrierRequest(CreateMutationRequest[RestCarrier]):
    """A request to create a rest carrier in a rhythmic scope at a measure position."""

    scope: Bound[RhythmicContainerParent]
    measure: Measure

    position: MeasurePosition
    written_value: DottedRhythmicValue


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRestCarrierRequest(DeleteMutationRequest[RestCarrier]):
    """A request to delete a rest carrier."""
