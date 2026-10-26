from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import ClefChange, OctaveTransposition
from piano_app.domain.score.document.services.mutation.compiler.intents import DeleteBatchIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    refuse_initial_context,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
    RemoveTarget,
)


class DeleteBatchCompiler:
    """Compiles one mixed delete gesture into a single remove request over the listed
    entities, in the order of their ids.

    Only addresses: what a listed entity already holds and the order of the deletions are
    decided on the live document by the analyzers. A measure goes by the measure removal
    rules. A grace group, item, carrier, note or rest goes as the analyzer decides on the
    live document: a group whose items all go goes whole. Voices and staffs are not deleted
    by this intent yet, and neither are anchors. The clef, key signature, tempo and dynamic at
    the very start of the score are never deleted: every score keeps them there
    (initial-clef-invariant). A clef and an octave line are refused too: each has a command of
    its own, which asks how its notes are treated.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: DeleteBatchIntent,
    ) -> Sequence[MutationRequest]:
        unique_ids: tuple[str, ...] = tuple(dict.fromkeys(intent.entity_ids))
        if not unique_ids:
            raise MutationRejectedError("Delete batch must contain at least one entity id.")

        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=unique_ids,
        )

        targets: list[RemoveTarget] = []
        unsupported_entities: list[ScoreEntity] = []
        for entity_id in unique_ids:
            entity: ScoreEntity = entities_by_id[entity_id]
            refuse_initial_context(document=document, entity=entity)
            if isinstance(entity, ClefChange | OctaveTransposition):
                raise MutationRejectedError(
                    "A clef or an octave line is deleted with its own command, "
                    "which asks how its notes are treated."
                )
            if isinstance(entity, RemoveTarget):
                targets.append(entity)
            else:
                unsupported_entities.append(entity)

        if unsupported_entities:
            targets_description: str = ", ".join(
                f"{type(entity).__name__}({entity.id!r})" for entity in unsupported_entities
            )
            raise MutationRejectedError(f"Unsupported delete targets: {targets_description}.")

        return [RemoveRequest(document=document, targets=tuple(targets))]
