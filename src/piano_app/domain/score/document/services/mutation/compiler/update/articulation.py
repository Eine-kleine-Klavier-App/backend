from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, with_articulation
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    SetArticulationIntent,
    ToggleArticulationIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateArticulationRequest,
)


class SetArticulationCompiler:
    """Compiles the marks of articulation of one note carrier into a single update request; a
    rest carrier has none and is refused."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetArticulationIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.carrier_id,),
        )
        carrier: NoteCarrier = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.carrier_id,
            expected=NoteCarrier,
        )

        return [UpdateArticulationRequest(target=carrier, articulations=intent.articulations)]


class ToggleArticulationCompiler:
    """Compiles taking one mark off a note carrier or putting it on into a single update
    request; the marks it excludes are replaced by it. A rest carrier is refused."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ToggleArticulationIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.carrier_id,),
        )
        carrier: NoteCarrier = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.carrier_id,
            expected=NoteCarrier,
        )

        articulations: frozenset[Articulation]
        if intent.articulation in carrier.articulations:
            articulations = carrier.articulations - {intent.articulation}
        else:
            articulations = with_articulation(
                current=carrier.articulations,
                added=intent.articulation,
            )

        return [UpdateArticulationRequest(target=carrier, articulations=articulations)]
