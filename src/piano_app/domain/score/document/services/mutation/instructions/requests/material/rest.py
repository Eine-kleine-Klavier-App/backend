from dataclasses import dataclass

from piano_app.domain.score.document.models.material import Rest
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff
from piano_app.domain.score.document.models.structural.rhythm import RhythmicContainerParent
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
    DeleteMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRestRequest(CreateMutationRequest[Rest]):
    """A request to create a rest in a rhythmic scope (a voice or a group), on a staff,
    at a measure position."""

    scope: Bound[RhythmicContainerParent]
    staff: Staff
    measure: Measure

    position: MeasurePosition
    written_value: DottedRhythmicValue


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRestRequest(DeleteMutationRequest[Rest]):
    """A request to delete a rest."""
