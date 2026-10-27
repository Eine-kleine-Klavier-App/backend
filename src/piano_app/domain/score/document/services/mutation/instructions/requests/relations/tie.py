from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTieRequest(CreateMutationRequest[Tie]):
    """A request to create a tie between two notes."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS
    creates: ClassVar[type[ScoreEntity]] = Tie

    start_note: Note
    end_note: Note
