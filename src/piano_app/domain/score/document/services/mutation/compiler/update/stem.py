from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    ResetStemIntent,
    SetStemIntent,
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
    UpdateStemRequest,
)


class SetStemCompiler:
    """Compiles a stem override for every listed note carrier into one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetStemIntent,
    ) -> Sequence[MutationRequest]:
        carrier_ids: tuple[str, ...] = tuple(dict.fromkeys(intent.carrier_ids))
        if not carrier_ids:
            raise MutationRejectedError("A stem edit must name at least one note carrier.")

        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=carrier_ids,
        )

        requests: list[MutationRequest] = []
        for carrier_id in carrier_ids:
            carrier: NoteCarrier = expect_entity(
                entities_by_id=entities_by_id,
                entity_id=carrier_id,
                expected=NoteCarrier,
            )
            requests.append(UpdateStemRequest(target=carrier, stem=intent.override))

        return requests


class ResetStemCompiler:
    """Compiles dropping the stem override of every listed note carrier into one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ResetStemIntent,
    ) -> Sequence[MutationRequest]:
        carrier_ids: tuple[str, ...] = tuple(dict.fromkeys(intent.carrier_ids))
        if not carrier_ids:
            raise MutationRejectedError("A stem edit must name at least one note carrier.")

        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=carrier_ids,
        )

        requests: list[MutationRequest] = []
        for carrier_id in carrier_ids:
            carrier: NoteCarrier = expect_entity(
                entities_by_id=entities_by_id,
                entity_id=carrier_id,
                expected=NoteCarrier,
            )
            requests.append(UpdateStemRequest(target=carrier, stem=None))

        return requests
