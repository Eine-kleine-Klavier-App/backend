from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
    DeleteMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRhythmicGroupRequest(CreateMutationRequest[GroupRhythmicContainer]):
    """A request to create an empty rhythmic group in a rhythmic scope at a measure
    position. ``occupied_size`` is read in the scope's units, ``written_size`` is the
    group's own interior."""

    scope: Bound[RhythmicContainerParent]
    measure: Measure
    position: MeasurePosition
    written_size: RhythmicSize
    occupied_size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRhythmicGroupRequest(DeleteMutationRequest[GroupRhythmicContainer]):
    """A request to delete a rhythmic group container."""
