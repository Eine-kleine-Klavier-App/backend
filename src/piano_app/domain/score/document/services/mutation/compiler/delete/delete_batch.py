from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import (
    CarrierOwner,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.compiler.intents import DeleteBatchIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import resolve_entities
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    DeleteNoteCarrierRequest,
    DeleteNoteRequest,
    DeleteRestCarrierRequest,
    DeleteRestRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteRhythmicGroupRequest,
)


class DeleteBatchCompiler:
    """Compiles one mixed delete gesture, pruning whatever a listed entity already holds.

    The order of the ids is retained within each level, while groups are emitted before
    carriers and carriers before primitives, because their analyzers own the downward
    cascade. Relation deletion is not supported by this intent yet.
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
        resolved_entities: list[ScoreEntity] = [
            entities_by_id[entity_id] for entity_id in unique_ids
        ]

        unsupported_entities: list[ScoreEntity] = [
            entity
            for entity in resolved_entities
            if not isinstance(
                entity, GroupRhythmicContainer | Note | NoteCarrier | Rest | RestCarrier
            )
        ]
        if unsupported_entities:
            targets_description: str = ", ".join(
                f"{type(entity).__name__}({entity.id!r})" for entity in unsupported_entities
            )
            raise MutationRejectedError(f"Unsupported delete targets: {targets_description}.")

        listed_groups: list[GroupRhythmicContainer] = [
            entity for entity in resolved_entities if isinstance(entity, GroupRhythmicContainer)
        ]
        groups: list[GroupRhythmicContainer] = [
            group for group in listed_groups if not _held(owner=group, groups=listed_groups)
        ]
        note_carriers: list[NoteCarrier] = [
            entity
            for entity in resolved_entities
            if isinstance(entity, NoteCarrier)
            and not _held(owner=entity.owner, groups=listed_groups)
        ]
        rest_carriers: list[RestCarrier] = [
            entity
            for entity in resolved_entities
            if isinstance(entity, RestCarrier)
            and not _held(owner=entity.owner, groups=listed_groups)
        ]
        notes: list[Note] = [
            entity
            for entity in resolved_entities
            if isinstance(entity, Note)
            and entity.note_carrier not in note_carriers
            and not _held(owner=entity.note_carrier.owner, groups=listed_groups)
        ]
        rests: list[Rest] = [
            entity
            for entity in resolved_entities
            if isinstance(entity, Rest)
            and entity.rest_carrier not in rest_carriers
            and not _held(owner=entity.rest_carrier.owner, groups=listed_groups)
        ]

        return [
            *(DeleteRhythmicGroupRequest(target=group) for group in groups),
            *(DeleteNoteCarrierRequest(target=carrier) for carrier in note_carriers),
            *(DeleteRestCarrierRequest(target=carrier) for carrier in rest_carriers),
            *(DeleteNoteRequest(target=note) for note in notes),
            *(DeleteRestRequest(target=rest) for rest in rests),
        ]


def _held(
    *,
    owner: CarrierOwner | RhythmicContainer,
    groups: list[GroupRhythmicContainer],
) -> bool:
    """Whether one of ``groups`` holds ``owner`` at any depth — that group's cascade
    already deletes it."""
    parent: RhythmicContainerParent | None = (
        owner.parent if isinstance(owner, RhythmicContainer) else None
    )
    while isinstance(parent, GroupRhythmicContainer):
        if parent in groups:
            return True

        parent = parent.parent

    return False
