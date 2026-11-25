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
    expect_voices,
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


def _steps_to(*, start: DynamicMarking, target: DynamicMarking) -> int:
    """The number of dynamic levels from the dynamic a voice starts at to the target."""
    steps: int = target.level - start.level
    if steps == 0:
        raise MutationRejectedError("A hairpin must change the dynamic.")

    return steps


class SetDynamicCompiler:
    """Compiles a dynamic for some voices into a create request for each voice."""

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

        return [
            CreateDynamicChangeRequest(
                measure=measure,
                position=intent.position,
                voice=voice,
                dynamic=intent.dynamic,
            )
            for voice in expect_voices(
                entities_by_id=entities_by_id, voice_ids=intent.voice_ids, mark="dynamic"
            )
        ]


class CreateHairpinCompiler:
    """Compiles a hairpin to a target dynamic into a create request for each voice; the target
    is turned into a number of levels from the dynamic its voice is at when the hairpin starts."""

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
        voices: tuple[Voice, ...] = expect_voices(
            entities_by_id=entities_by_id, voice_ids=intent.voice_ids, mark="hairpin"
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
                voice=voice,
                steps=_steps_to(
                    start=values.dynamic_at(voice=voice, at=start_at), target=intent.target
                ),
            )
            for voice in voices
        ]


class SetHairpinTargetCompiler:
    """Compiles a new target of hairpins into an update request for each."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetHairpinTargetIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=intent.hairpin_ids,
        )
        hairpins: list[Hairpin] = [
            expect_entity(entities_by_id=entities_by_id, entity_id=hairpin_id, expected=Hairpin)
            for hairpin_id in intent.hairpin_ids
        ]

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        values: ContextValues = ContextValues(
            contexts=ContextIndex(document=document, geometry=geometry), geometry=geometry
        )

        return [
            UpdateHairpinStepsRequest(
                target=hairpin,
                steps=_steps_to(
                    start=values.hairpin_start_dynamic(hairpin=hairpin, voice=hairpin.voice),
                    target=intent.target,
                ),
            )
            for hairpin in hairpins
        ]
