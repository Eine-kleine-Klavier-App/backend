from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import InsertRestIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    PlaceSpansRequest,
    RestContent,
)


class InsertRestCompiler:
    """Compiles a rest insert into one request, like a note insert: its spans are placed —
    cut at the barlines into untied rests, writing over what they meet and never joining
    it.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: InsertRestIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
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

        return [
            PlaceSpansRequest(
                voice=voice,
                measure=measure,
                position=intent.position,
                written_length=intent.written_value.fraction,
                content=RestContent(staff=staff),
            ),
        ]
