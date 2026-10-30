from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteAction,
    DeleteNoteAction,
    UpdateFingeringAction,
    UpdateNotePitchAction,
    UpdateStaffStepAction,
)


class CreateNoteHandler:
    """Creates a note inside its carrier."""

    def handle(
        self,
        *,
        action: CreateNoteAction,
        sink: MutationSink,
    ) -> Note:
        carrier: NoteCarrier = action.note_carrier
        note: Note = Note.create(
            note_carrier=carrier,
            staff=action.staff,
            staff_step=action.staff_step,
            accidental=action.accidental,
            fingering=action.fingering,
            sink=sink,
        )
        return note


class DeleteNoteHandler:
    """Detaches a note from its carrier."""

    def handle(
        self,
        *,
        action: DeleteNoteAction,
        sink: MutationSink,
    ) -> None:
        note: Note = action.target
        note.detach(sink=sink)
        return None


class UpdateFingeringHandler:
    """Sets a note's fingering."""

    def handle(
        self,
        *,
        action: UpdateFingeringAction,
        sink: MutationSink,
    ) -> None:
        note: Note = action.target
        note.set_fingering(fingering=action.fingering, sink=sink)
        return None


class UpdateStaffStepHandler:
    """Moves a note to another staff step."""

    def handle(
        self,
        *,
        action: UpdateStaffStepAction,
        sink: MutationSink,
    ) -> None:
        note: Note = action.target
        note.set_staff_step(staff_step=action.staff_step, sink=sink)
        return None


class UpdateNotePitchHandler:
    """Puts a note on a staff, at a staff step, with an accidental."""

    def handle(
        self,
        *,
        action: UpdateNotePitchAction,
        sink: MutationSink,
    ) -> None:
        note: Note = action.target
        if action.staff is not note.staff:
            note.set_staff(staff=action.staff, sink=sink)

        note.set_staff_step(staff_step=action.staff_step, sink=sink)
        note.set_accidental(accidental=action.accidental, sink=sink)
        return None
