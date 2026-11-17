from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateRefrainIntent,
    MoveRefrainEndIntent,
    MoveRefrainStartIntent,
    SetRefrainTimesIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateRefrainRequest,
    MoveRefrainEndRequest,
    MoveRefrainStartRequest,
    UpdateRefrainTimesRequest,
)


class CreateRefrainCompiler:
    """Compiles a refrain of a stretch of the whole score into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateRefrainIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        if (intent.end_measure_id is None) != (intent.end_position is None):
            raise MutationRejectedError("A refrain's end is a measure and a position, or neither.")

        entity_ids: tuple[str, ...] = (
            (intent.start_measure_id,)
            if intent.end_measure_id is None
            else (intent.start_measure_id, intent.end_measure_id)
        )
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities, entity_ids=entity_ids
        )
        end_measure: Measure | None = (
            None
            if intent.end_measure_id is None
            else expect_entity(
                entities_by_id=entities_by_id, entity_id=intent.end_measure_id, expected=Measure
            )
        )

        return [
            CreateRefrainRequest(
                start_measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.start_measure_id,
                    expected=Measure,
                ),
                start_position=intent.start_position,
                end_measure=end_measure,
                end_position=intent.end_position,
                times=intent.times,
            )
        ]


class SetRefrainTimesCompiler:
    """Compiles a new number of times of a refrain into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetRefrainTimesIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities, entity_ids=(intent.refrain_id,)
        )
        refrain: Refrain = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.refrain_id, expected=Refrain
        )

        return [UpdateRefrainTimesRequest(target=refrain, times=intent.times)]


class MoveRefrainStartCompiler:
    """Compiles a new start of a refrain into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveRefrainStartIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities, entity_ids=(intent.refrain_id, intent.measure_id)
        )

        return [
            MoveRefrainStartRequest(
                target=expect_entity(
                    entities_by_id=entities_by_id, entity_id=intent.refrain_id, expected=Refrain
                ),
                measure=expect_entity(
                    entities_by_id=entities_by_id, entity_id=intent.measure_id, expected=Measure
                ),
                position=intent.position,
            )
        ]


class MoveRefrainEndCompiler:
    """Compiles a new end of a refrain into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveRefrainEndIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        if (intent.measure_id is None) != (intent.position is None):
            raise MutationRejectedError("A refrain's end is a measure and a position, or neither.")

        entity_ids: tuple[str, ...] = (
            (intent.refrain_id,)
            if intent.measure_id is None
            else (intent.refrain_id, intent.measure_id)
        )
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities, entity_ids=entity_ids
        )

        return [
            MoveRefrainEndRequest(
                target=expect_entity(
                    entities_by_id=entities_by_id, entity_id=intent.refrain_id, expected=Refrain
                ),
                measure=(
                    None
                    if intent.measure_id is None
                    else expect_entity(
                        entities_by_id=entities_by_id, entity_id=intent.measure_id, expected=Measure
                    )
                ),
                position=intent.position,
            )
        ]
