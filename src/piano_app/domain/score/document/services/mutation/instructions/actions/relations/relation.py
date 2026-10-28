from dataclasses import dataclass

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.relations.start_end import NoteToNoteRelation
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRelationAction(DeleteMutationAction[Relation]):
    """Deletes a relation."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRelationStartAction(UpdateMutationAction[NoteToNoteRelation]):
    """Moves a note-to-note relation's start to another note."""

    start_note: Note
