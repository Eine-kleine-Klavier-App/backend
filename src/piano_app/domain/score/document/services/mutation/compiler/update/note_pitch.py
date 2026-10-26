from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import host_leaf_of
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    ChangePitchIntent,
    MoveNoteToStaffIntent,
    PitchEditMode,
    SetAccidentalIntent,
    ShiftStaffStepsIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateNotePitchRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class ChangePitchCompiler:
    """Compiles putting a note on another step of its staff into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ChangePitchIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.note_id,),
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.note_id,
            expected=Note,
        )

        return [
            UpdateNotePitchRequest(
                target=note,
                staff=note.staff,
                staff_step=intent.staff_step,
                accidental=note.accidental,
            )
        ]


class SetAccidentalCompiler:
    """Compiles giving a note another accidental into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetAccidentalIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.note_id,),
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.note_id,
            expected=Note,
        )

        return [
            UpdateNotePitchRequest(
                target=note,
                staff=note.staff,
                staff_step=note.staff_step,
                accidental=intent.accidental,
            )
        ]


class MoveNoteToStaffCompiler:
    """Compiles moving a note to another staff into one update request; pitch-preserving, the
    step that sounds as before on the new staff is worked out here from the document."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveNoteToStaffIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.note_id, intent.staff_id),
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.note_id,
            expected=Note,
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )

        staff_step: int = note.staff_step
        if intent.mode is PitchEditMode.PRESERVE_PITCH:
            owner = host_leaf_of(note=note)
            if owner is None:
                raise MutationRejectedError("Only a note in a metric leaf keeps its pitch.")

            geometry: ScoreGeometry = ScoreGeometry(document=document)
            pitch: ScorePitch = ScorePitch(
                document=document,
                geometry=geometry,
                contexts=ContextIndex(document=document, geometry=geometry),
            )
            staff_step = pitch.staff_step_for(
                staff=staff,
                point=geometry.point_of(anchor=owner.anchor),
                midi_note=pitch.pitch_of(note=note).midi_note,
                accidental=note.accidental,
            )

        return [
            UpdateNotePitchRequest(
                target=note,
                staff=staff,
                staff_step=staff_step,
                accidental=note.accidental,
            )
        ]


class ShiftStaffStepsCompiler:
    """Snapshot all selected targets before tie propagation can change a later note."""

    def compile(
        self, *, document: ScoreDocument, intent: ShiftStaffStepsIntent
    ) -> Sequence[MutationRequest]:
        if not intent.note_ids or intent.delta not in (-1, 1):
            raise MutationRejectedError("Select notes and shift by one staff step.")
        ids = tuple(dict.fromkeys(intent.note_ids))
        entities = resolve_entities(document=document, entity_ids=ids)
        notes = [expect_entity(entities_by_id=entities, entity_id=id, expected=Note) for id in ids]
        delta = intent.delta
        if len(notes) == 1 and len(notes[0].note_carrier.notes) > 1:
            note = notes[0]
            owner = host_leaf_of(note=note)
            if owner is None:
                raise MutationRejectedError("Only a note in a metric leaf skips a unison.")
            geometry = ScoreGeometry(document=document)
            pitch = ScorePitch(
                document=document,
                geometry=geometry,
                contexts=ContextIndex(document=document, geometry=geometry),
            )
            candidate = pitch.resolve(
                staff=note.staff,
                point=geometry.point_of(anchor=owner.anchor),
                staff_step=note.staff_step + delta,
                accidental=note.accidental,
            )
            if any(
                other is not note and pitch.pitch_of(note=other).midi_note == candidate.midi_note
                for other in note.note_carrier.notes
            ):
                delta *= 2
        return [
            UpdateNotePitchRequest(
                target=note,
                staff=note.staff,
                staff_step=note.staff_step + delta,
                accidental=note.accidental,
            )
            for note in notes
        ]
