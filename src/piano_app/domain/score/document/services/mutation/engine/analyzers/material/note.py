from collections.abc import Sequence

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations import Relation, Tie
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteAction,
    UpdateFingeringAction,
    UpdateNotePitchAction,
    UpdateStaffStepAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
    UpdateFingeringRequest,
    UpdateNotePitchRequest,
    UpdateStaffStepRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class CreateNoteAnalyzer:
    """Creates a note in the carrier its request names.

    Where the carrier comes from — a new one or a chord joined — is decided above, by the
    spans; a note decides nothing beyond itself.
    """

    def analyze(
        self,
        *,
        request: CreateNoteRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        # TODO:
        #   PITCH-VALIDATION (deferred — pitch is not in v1): when the carrier already
        #   holds a note at the SAME pitch, chord-duplicate is forbidden → reject (or
        #   replace); cross-voice unison stays allowed. See [[pitch-and-voice-policy]].
        #   No-op until pitch lands.
        yield CreateNoteAction(
            note_carrier=request.carrier,
            staff=request.staff,
            staff_step=request.staff_step,
            accidental=request.accidental,
            fingering=request.fingering,
        )


def cascade_note(*, target: Note) -> Sequence[Deletable]:
    """Decides the note's deletion cascade.

    Note-to-note relations are deleted before the note. Cleanup of an empty carrier is
    deferred to the mutation boundary.
    """
    # a snapshot: each relation's deletion removes it from the note's own list
    doomed_relations: list[Relation] = list(target.relations)

    return doomed_relations


class UpdateFingeringAnalyzer:
    """Decides nothing: a fingering guards no invariant of the music, and nothing reads
    it to decide."""

    def analyze(
        self,
        *,
        request: UpdateFingeringRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield UpdateFingeringAction(target=request.target, fingering=request.fingering)


class UpdateStaffStepAnalyzer:
    """Decides nothing: what the new place sounds like is judged at the boundary, where chords
    and ties are checked for the pitches they hold."""

    def analyze(
        self,
        *,
        request: UpdateStaffStepRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield UpdateStaffStepAction(target=request.target, staff_step=request.staff_step)


class UpdateNotePitchAnalyzer:
    """Puts a note on a staff, at a staff step, with an accidental, and carries what it now
    sounds like along its ties (tie-propagation).

    The note changes first. Then each note tied to it takes the same accidental and the staff
    step that sounds the same where it lies, which another clef or octave line may make a
    different step; a neighbour already there emits nothing, which ends the chain.
    """

    def analyze(
        self,
        *,
        request: UpdateNotePitchRequest,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis:
        note: Note = request.target
        yield UpdateNotePitchAction(
            target=note,
            staff=request.staff,
            staff_step=request.staff_step,
            accidental=request.accidental,
        )

        sounding: int = pitch.pitch_of(note=note).midi_note
        for relation in list(note.relations):
            if not isinstance(relation, Tie):
                continue

            neighbour: Note = relation.end if relation.start is note else relation.start
            owner: object = neighbour.note_carrier.owner
            if not isinstance(owner, LeafRhythmicContainer):
                continue

            staff_step: int = pitch.staff_step_for(
                staff=neighbour.staff,
                point=geometry.point_of(anchor=owner.anchor),
                midi_note=sounding,
                accidental=request.accidental,
            )
            if neighbour.staff_step != staff_step or neighbour.accidental is not request.accidental:
                yield UpdateNotePitchRequest(
                    target=neighbour,
                    staff=neighbour.staff,
                    staff_step=staff_step,
                    accidental=request.accidental,
                )
