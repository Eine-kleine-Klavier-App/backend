from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.relations.start_end import NoteToNoteRelation
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckRelationRequest(MutationRequest):
    """A request to judge ``relation`` by the rules of its kind: left alone when it holds,
    repaired or removed when it is broken."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    relation: Relation


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRelationStartRequest(UpdateMutationRequest[NoteToNoteRelation]):
    """A request to move a note-to-note relation's start to ``start_note``."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    start_note: Note
