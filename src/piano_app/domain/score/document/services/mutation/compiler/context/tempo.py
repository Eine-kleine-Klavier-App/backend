from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import TempoTransition
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicValue
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.contexts import (
    ContextIndex,
    ContextValues,
    Tempo,
    global_position,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateTempoTransitionIntent,
    SetTempoIntent,
    SetTempoTransitionTargetIntent,
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
    CreateTempoChangeRequest,
    CreateTempoTransitionRequest,
    UpdateTempoTransitionRatioRequest,
)


class SetTempoCompiler:
    """Compiles a tempo into one create request. A word without a number gets the middle of
    its usual range, in quarter notes; a number needs its beat."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetTempoIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.measure_id,),
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )

        beat: DottedRhythmicValue
        bpm: int
        if intent.bpm is not None:
            if intent.beat is None:
                raise MutationRejectedError("A tempo with a number names its beat.")

            beat, bpm = intent.beat, intent.bpm
        elif intent.label is not None:
            beat, bpm = DottedRhythmicValue(value=RhythmicValue.QUARTER), intent.label.typical_bpm
        else:
            raise MutationRejectedError("A tempo gives a number, a word, or both.")

        return [
            CreateTempoChangeRequest(
                measure=measure,
                position=intent.position,
                beat=beat,
                bpm=bpm,
                show_label=intent.show_label or intent.label is not None,
            )
        ]


def _ratio_to(*, start: Tempo, target_bpm: int) -> Fraction:
    """The ratio of speed from ``start`` to ``target_bpm`` beats per minute of its beat."""
    if target_bpm < 1:
        raise MutationRejectedError("A tempo is at least 1 beat per minute.")

    ratio: Fraction = Fraction(target_bpm) / start.bpm
    if ratio == 1:
        raise MutationRejectedError("A tempo transition must change the tempo.")

    return ratio


class CreateTempoTransitionCompiler:
    """Compiles a gradual tempo change to a target tempo into one create request; the target
    is turned into a ratio of speed to the tempo in force at the start."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateTempoTransitionIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.start_measure_id, intent.end_measure_id),
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

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        start: Tempo = ContextValues(
            contexts=ContextIndex(document=document, geometry=geometry), geometry=geometry
        ).tempo_at(
            at=global_position(
                geometry=geometry, measure=start_measure, position=intent.start_position
            )
        )

        return [
            CreateTempoTransitionRequest(
                start_measure=start_measure,
                start_position=intent.start_position,
                end_measure=end_measure,
                end_position=intent.end_position,
                ratio=_ratio_to(start=start, target_bpm=intent.target_bpm),
            )
        ]


class SetTempoTransitionTargetCompiler:
    """Compiles a new target of a tempo transition into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetTempoTransitionTargetIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.transition_id,),
        )
        transition: TempoTransition = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.transition_id,
            expected=TempoTransition,
        )

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        start: Tempo = ContextValues(
            contexts=ContextIndex(document=document, geometry=geometry), geometry=geometry
        ).transition_start_tempo(transition=transition)

        return [
            UpdateTempoTransitionRatioRequest(
                target=transition,
                ratio=_ratio_to(start=start, target_bpm=intent.target_bpm),
            )
        ]
