from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)

# a plain alias, not a ``type`` statement: the delete batch compiler checks ids against it
# with ``isinstance``, so the accepted kinds are listed once
RemoveTarget = (
    GroupRhythmicContainer
    | LeafRhythmicContainer
    | NoteCarrier
    | RestCarrier
    | Note
    | Rest
    | GraceGroup
    | GraceItem
    | Relation
    | Context
    | Measure
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveRequest(MutationRequest):
    """A request to remove several entities of ``document`` in one intent — groups, leaves,
    note and rest carriers, single notes and rests, grace groups and items, relations, contexts
    and measures.
    Whatever one of them holds goes with it."""

    axis: ClassVar[Axis | None] = Axis.INTENT

    document: ScoreDocument
    targets: tuple[RemoveTarget, ...]
