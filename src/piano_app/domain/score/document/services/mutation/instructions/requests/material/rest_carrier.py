from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import RestCarrier
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRestCarrierRequest(CreateMutationRequest[RestCarrier]):
    """A request to create a rest carrier on a given leaf or grace item."""

    axis: ClassVar[Axis | None] = Axis.CONTENT
    creates: ClassVar[type[ScoreEntity]] = RestCarrier

    owner: LeafRhythmicContainer | GraceItem
