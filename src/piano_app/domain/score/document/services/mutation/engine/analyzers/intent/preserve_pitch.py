from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    PreservePitchRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateStaffStepRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class PreservePitchAnalyzer:
    """Runs context edits that change what the notes of some staffs sound like, keeping what
    each note sounds like (pitch-preserving, as against step-preserving where the notes stay
    put and sound different).

    Before the first yield it reads every note of the staffs that sits in a metric leaf or among its
    grace notes, with
    what it sounds like; a note with no clef in force is a broken state and raises. The edits
    run in order. Then each such note whose staff step no longer sounds as before moves to the
    step that does, with the same accidental — always possible, as every white key sits on some
    step whatever the clef.
    """

    def analyze(
        self,
        *,
        request: PreservePitchRequest,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis:
        staffs: tuple[Staff, ...] = request.staffs

        sounding: list[tuple[Note, LeafRhythmicContainer, int]] = []
        for voice in request.document.voices:
            for leaf in iter_leaves(voice):
                carriers: list[Carrier | None] = [leaf.carrier]
                for group in (leaf.grace_before, leaf.grace_after):
                    if group is not None:
                        carriers.extend(item.carrier for item in group.grace_items)

                for carrier in carriers:
                    if not isinstance(carrier, NoteCarrier):
                        continue

                    for note in carrier.notes:
                        if note.staff not in staffs:
                            continue

                        sounding.append((note, leaf, pitch.pitch_of(note=note).midi_note))

        # not ``yield from``: what each edit produces is sent back to this generator
        for edit in request.requests:  # noqa: UP028
            yield edit

        for note, leaf, midi_note in sounding:
            staff_step: int = pitch.staff_step_for(
                staff=note.staff,
                point=geometry.point_of(anchor=leaf.anchor),
                midi_note=midi_note,
                accidental=note.accidental,
            )

            if staff_step != note.staff_step:
                yield UpdateStaffStepRequest(target=note, staff_step=staff_step)
