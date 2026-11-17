from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import Hairpin
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import Measure, Voice
from piano_app.domain.score.document.services.contexts import (
    ContextIndex,
    ContextValues,
    global_position,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateHairpinIntent,
    SetDynamicIntent,
    SetHairpinTargetIntent,
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
    CreateDynamicChangeRequest,
    CreateHairpinRequest,
    UpdateHairpinStepsRequest,
)


def _steps_to(*, starts: Sequence[DynamicMarking], target: DynamicMarking) -> int:
    """The number of dynamic levels from the one dynamic all the voices start at to the
    target; the voices starting at different dynamics cannot share one target."""
    if len(set(starts)) != 1:
        raise MutationRejectedError("The voices of a hairpin must start at the same dynamic.")

    steps: int = target.level - starts[0].level
    if steps == 0:
        raise MutationRejectedError("A hairpin must change the dynamic.")

    return steps


class SetDynamicCompiler:
    """Compiles a dynamic for some voices into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetDynamicIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.measure_id, *intent.voice_ids),
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )
        voices: tuple[Voice, ...] = tuple(
            expect_entity(entities_by_id=entities_by_id, entity_id=voice_id, expected=Voice)
            for voice_id in intent.voice_ids
        )

        return [
            CreateDynamicChangeRequest(
                measure=measure,
                position=intent.position,
                voices=voices,
                dynamic=intent.dynamic,
            )
        ]


class CreateHairpinCompiler:
    """Compiles a hairpin to a target dynamic into one create request; the target is turned
    into a number of levels from the dynamic in force at the start."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateHairpinIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.start_measure_id, intent.end_measure_id, *intent.voice_ids),
        )
        start_measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.start_measure_id,
            expected=Measure,
        )
        end_measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.end_measure_id,
            expected=Measure,
        )
        voices: tuple[Voice, ...] = tuple(
            expect_entity(entities_by_id=entities_by_id, entity_id=voice_id, expected=Voice)
            for voice_id in intent.voice_ids
        )

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        values: ContextValues = ContextValues(
            contexts=ContextIndex(document=document, geometry=geometry), geometry=geometry
        )
        start_at = global_position(
            geometry=geometry, measure=start_measure, position=intent.start_position
        )

        return [
            CreateHairpinRequest(
                start_measure=start_measure,
                start_position=intent.start_position,
                end_measure=end_measure,
                end_position=intent.end_position,
                voices=voices,
                steps=_steps_to(
                    starts=[values.dynamic_at(voice=voice, at=start_at) for voice in voices],
                    target=intent.target,
                ),
            )
        ]


class SetHairpinTargetCompiler:
    """Compiles a new target of a hairpin into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetHairpinTargetIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.hairpin_id,),
        )
        hairpin: Hairpin = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.hairpin_id,
            expected=Hairpin,
        )

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        values: ContextValues = ContextValues(
            contexts=ContextIndex(document=document, geometry=geometry), geometry=geometry
        )

        return [
            UpdateHairpinStepsRequest(
                target=hairpin,
                steps=_steps_to(
                    starts=[
                        values.hairpin_start_dynamic(hairpin=hairpin, voice=voice)
                        for voice in hairpin.voices
                    ],
                    target=intent.target,
                ),
            )
        ]
