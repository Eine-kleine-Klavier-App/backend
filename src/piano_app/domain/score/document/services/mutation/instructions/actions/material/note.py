from dataclasses import dataclass

from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, Fingering
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateNoteAction(CreateMutationAction[Note]):
    """Creates a note inside a carrier."""

    note_carrier: NoteCarrier
    staff: Staff
    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteNoteAction(DeleteMutationAction[Note]):
    """Deletes a note."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateFingeringAction(UpdateMutationAction[Note]):
    """Sets a note's fingering."""

    fingering: Fingering


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateStaffStepAction(UpdateMutationAction[Note]):
    """Moves a note to another staff step."""

    staff_step: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateNotePitchAction(UpdateMutationAction[Note]):
    """Puts a note on a staff, at a staff step, with an accidental."""

    staff: Staff
    staff_step: int
    accidental: Accidental
