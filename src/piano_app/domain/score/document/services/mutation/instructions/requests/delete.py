from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    DeleteMutationRequest,
)

type Deletable = (
    Note
    | NoteCarrier
    | Rest
    | RestCarrier
    | LeafRhythmicContainer
    | GraceGroup
    | GraceItem
    | GroupRhythmicContainer
    | TemporalAnchor
    | Relation
    | Context
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRequest(DeleteMutationRequest[Deletable]):
    """A request to delete ``target`` with everything that must not outlive it.

    It belongs to no axis: it may be yielded from anywhere and is held to the axis of its
    nearest axis-bearing ancestor. What it yields is only more deletes, so it opens no
    upward path.
    """

    axis: ClassVar[Axis | None] = None
