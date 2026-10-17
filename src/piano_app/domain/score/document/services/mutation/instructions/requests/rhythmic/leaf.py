from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
    DeleteMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateLeafRequest(CreateMutationRequest[LeafRhythmicContainer]):
    """A request to create a leaf rhythmic container in a rhythmic scope at a measure
    position. The scope is decided by whoever issues the root request; the leaf never
    descends on its own."""

    scope: Bound[RhythmicContainerParent]
    measure: Measure
    position: MeasurePosition
    size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteLeafRequest(DeleteMutationRequest[LeafRhythmicContainer]):
    """A request to delete a leaf rhythmic container."""
