from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Rest, RestCarrier
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRestRequest(CreateMutationRequest[Rest]):
    """A request to create a rest in a given rest carrier, on a staff."""

    axis: ClassVar[Axis | None] = Axis.CONTENT
    creates: ClassVar[type[ScoreEntity]] = Rest

    carrier: RestCarrier
    staff: Staff
