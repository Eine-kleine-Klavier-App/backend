from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent
from piano_app.domain.score.document.services.mutation.compiler.intents.context.mode import (
    PitchEditMode,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangePitchIntent(EditIntent):
    """Put a note on another step of its staff; the accidental stays. The notes it is tied to
    follow."""

    note_id: str
    staff_step: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SetAccidentalIntent(EditIntent):
    """Give a note another accidental; it stays on its step, so it sounds different. The notes
    it is tied to follow."""

    note_id: str
    accidental: Accidental


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveNoteToStaffIntent(EditIntent):
    """Move a note to another staff: pitch-preserving it takes the step that sounds as before,
    step-preserving it keeps its step and sounds different, and the notes it is tied to
    follow."""

    note_id: str
    staff_id: str
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class ShiftStaffStepsIntent(EditIntent):
    """Shift selected notes by a relative staff step in one gesture; accidentals stay."""

    note_ids: tuple[str, ...]
    delta: int
