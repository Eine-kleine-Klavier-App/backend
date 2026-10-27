from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, Fingering
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateNoteRequest(CreateMutationRequest[Note]):
    """A request to create a note in a given note carrier, on a staff."""

    axis: ClassVar[Axis | None] = Axis.CONTENT
    creates: ClassVar[type[ScoreEntity]] = Note

    carrier: NoteCarrier
    staff: Staff

    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateFingeringRequest(UpdateMutationRequest[Note]):
    """A request to set a note's fingering."""

    axis: ClassVar[Axis | None] = Axis.CONTENT

    fingering: Fingering


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateStaffStepRequest(UpdateMutationRequest[Note]):
    """A request to move a note to another staff step, keeping the note."""

    axis: ClassVar[Axis | None] = Axis.CONTENT

    staff_step: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateNotePitchRequest(UpdateMutationRequest[Note]):
    """A request to put a note on a staff, at a staff step, with an accidental: what it sounds
    like changes, and the notes it is tied to follow."""

    axis: ClassVar[Axis | None] = Axis.CONTENT

    staff: Staff
    staff_step: int
    accidental: Accidental
