from collections.abc import Sequence
from itertools import pairwise

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations.start_end import Tie
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.services.mutation.compiler.intents import InsertNoteIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    Placement,
    expect_entity,
    place,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRequest,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)


class InsertNoteCompiler:
    """Compiles a note insert: the note is placed, cut at the barlines it crosses, and
    its parts are tied into one sounding note.

    The ties come after all the notes: the drain runs each note's chain in full before
    the next request, so every part is live by the time a tie resolves it.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: InsertNoteIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.voice_id, intent.staff_id, intent.measure_id),
        )
        voice: Voice = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.voice_id,
            expected=Voice,
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )

        parts: list[Placement] = place(
            voice=voice,
            measure=measure,
            position=intent.position,
            length=intent.written_value.fraction,
        )

        requests: list[MutationRequest] = []
        notes: list[ResultRef[Note]] = []

        # the pitch and the fingering go on every part; showing them only on the first
        # is a display concern
        for part in parts:
            note: ResultRef[Note] = ResultRef[Note]()
            requests.append(
                CreateNoteRequest(
                    scope=part.scope,
                    staff=staff,
                    measure=part.measure,
                    position=part.position,
                    written_value=part.written_value,
                    staff_step=intent.staff_step,
                    accidental=intent.accidental,
                    fingering=intent.fingering,
                    out=note,
                )
            )
            notes.append(note)

        for start_note, end_note in pairwise(notes):
            requests.append(
                CreateTieRequest(
                    start_note=start_note,
                    end_note=end_note,
                    out=ResultRef[Tie](),
                )
            )

        return requests
