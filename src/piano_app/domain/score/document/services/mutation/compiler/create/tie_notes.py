from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.mutation.compiler.intents import TieNotesIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateArticulationRequest,
    UpdateOrnamentRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)


class TieNotesCompiler:
    """Compiles a tie between two existing notes into a tie request.

    When every note of the second carrier ends a tie once this one exists, the carrier only
    continues the first, and its articulations and ornament are overwritten with the first's
    before the tie is made (the marks of a carrier are otherwise independent of ties). A
    carrier with a new note of its own keeps its marks.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: TieNotesIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.start_note_id, intent.end_note_id),
        )
        start_note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.start_note_id,
            expected=Note,
        )
        end_note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.end_note_id,
            expected=Note,
        )

        requests: list[MutationRequest] = []
        start_carrier: NoteCarrier = start_note.note_carrier
        end_carrier: NoteCarrier = end_note.note_carrier
        if all(
            note is end_note
            or any(
                isinstance(relation, Tie) and relation.end is note for relation in note.relations
            )
            for note in end_carrier.notes
        ):
            if end_carrier.articulations != start_carrier.articulations:
                requests.append(
                    UpdateArticulationRequest(
                        target=end_carrier,
                        articulations=start_carrier.articulations,
                    )
                )

            if end_carrier.ornament is not start_carrier.ornament:
                requests.append(
                    UpdateOrnamentRequest(target=end_carrier, ornament=start_carrier.ornament)
                )

        requests.append(CreateTieRequest(start_note=start_note, end_note=end_note))

        return requests
