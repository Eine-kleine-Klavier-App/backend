from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CarrierMarks,
    SetCarrierMarksIntent,
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
    UpdateArticulationRequest,
    UpdateOrnamentRequest,
)


class SetCarrierMarksCompiler:
    """Compiles the marks of several note carriers into one update request per mark, so the
    whole batch is one gesture. A rest carrier, an unknown id, a carrier named twice, an empty
    batch or an item that sets nothing is refused."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetCarrierMarksIntent,
    ) -> Sequence[MutationRequest]:
        if not intent.items:
            raise MutationRejectedError("A batch of marks names at least one carrier.")

        carrier_ids: list[str] = [item.carrier_id for item in intent.items]
        if len(set(carrier_ids)) != len(carrier_ids):
            raise MutationRejectedError("A batch of marks names each carrier once.")

        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=carrier_ids,
        )

        requests: list[MutationRequest] = []
        item: CarrierMarks
        for item in intent.items:
            if item.articulations is None and item.ornament is None:
                raise MutationRejectedError("An item of a batch of marks sets something.")

            carrier: NoteCarrier = expect_entity(
                entities_by_id=entities_by_id,
                entity_id=item.carrier_id,
                expected=NoteCarrier,
            )
            if item.articulations is not None:
                requests.append(
                    UpdateArticulationRequest(target=carrier, articulations=item.articulations)
                )

            if item.ornament is not None:
                requests.append(UpdateOrnamentRequest(target=carrier, ornament=item.ornament))

        return requests
