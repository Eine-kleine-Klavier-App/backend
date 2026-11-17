from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    OctaveTransposition,
    SpanContext,
)
from piano_app.domain.score.document.models.structural import MEASURE_START, Measure, Staff, Voice
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateOctaveTranspositionIntent,
    CreateSlurIntent,
    CreateSustainHoldIntent,
    DeleteClefIntent,
    DeleteOctaveTranspositionIntent,
    MoveContextEndIntent,
    MoveContextStartIntent,
    OpenContextEndIntent,
    SetClefIntent,
    SetKeySignatureIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    in_mode,
    refuse_initial_context,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateKeySignatureChangeRequest,
    CreateOctaveTranspositionRequest,
    CreateSlurRequest,
    CreateSustainHoldRequest,
    OpenContextEndRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


class SetKeySignatureCompiler:
    """Compiles a key signature for a staff into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetKeySignatureIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.staff_id, intent.measure_id),
        )

        return [
            CreateKeySignatureChangeRequest(
                measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.measure_id,
                    expected=Measure,
                ),
                position=intent.position,
                staff=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.staff_id,
                    expected=Staff,
                ),
                alterations=intent.alterations,
            )
        ]


class CreateSlurCompiler:
    """Compiles a slur for some voices into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateSlurIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.start_measure_id, intent.end_measure_id, *intent.voice_ids),
        )

        return [
            CreateSlurRequest(
                start_measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.start_measure_id,
                    expected=Measure,
                ),
                start_position=intent.start_position,
                end_measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.end_measure_id,
                    expected=Measure,
                ),
                end_position=intent.end_position,
                voices=tuple(
                    expect_entity(entities_by_id=entities_by_id, entity_id=voice_id, expected=Voice)
                    for voice_id in intent.voice_ids
                ),
            )
        ]


class CreateSustainHoldCompiler:
    """Compiles a sustain hold between two places into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateSustainHoldIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.start_measure_id, intent.end_measure_id),
        )

        return [
            CreateSustainHoldRequest(
                start_measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.start_measure_id,
                    expected=Measure,
                ),
                start_position=intent.start_position,
                end_measure=expect_entity(
                    entities_by_id=entities_by_id,
                    entity_id=intent.end_measure_id,
                    expected=Measure,
                ),
                end_position=intent.end_position,
            )
        ]


class CreateOctaveTranspositionCompiler:
    """Compiles an octave transposition for a staff into one create request, under a
    pitch-preserving request when the notes it reaches are to sound as before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateOctaveTranspositionIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.staff_id, intent.start_measure_id, intent.end_measure_id),
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )

        return in_mode(
            document=document,
            staff=staff,
            mode=intent.mode,
            requests=[
                CreateOctaveTranspositionRequest(
                    start_measure=expect_entity(
                        entities_by_id=entities_by_id,
                        entity_id=intent.start_measure_id,
                        expected=Measure,
                    ),
                    start_position=intent.start_position,
                    end_measure=expect_entity(
                        entities_by_id=entities_by_id,
                        entity_id=intent.end_measure_id,
                        expected=Measure,
                    ),
                    end_position=intent.end_position,
                    staff=staff,
                    octaves=intent.octaves,
                )
            ],
        )


class SetClefCompiler:
    """Compiles a clef for a staff into one create request, under a pitch-preserving request
    when the notes it reaches are to sound as before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetClefIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.staff_id, intent.measure_id),
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )

        return in_mode(
            document=document,
            staff=staff,
            mode=intent.mode,
            requests=[
                CreateClefChangeRequest(
                    measure=expect_entity(
                        entities_by_id=entities_by_id,
                        entity_id=intent.measure_id,
                        expected=Measure,
                    ),
                    position=intent.position,
                    staff=staff,
                    clef=intent.clef,
                    octave_transposition=intent.octave_transposition,
                )
            ],
        )


class DeleteClefCompiler:
    """Compiles taking a clef out of some measures into one request, under a pitch-preserving
    request when the notes it reached are to sound as before.

    The clef returns at the start of the measure after the last one chosen: its start moves
    there, the way a clef of a removed measure does. When its stretch ends before that point —
    another clef of the staff starts at or before it — or no measure follows, it is deleted.
    The clef at the start of the score is never taken out.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: DeleteClefIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.clef_id, *intent.measure_ids),
        )
        clef: ClefChange = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.clef_id,
            expected=ClefChange,
        )
        refuse_initial_context(document=document, entity=clef)

        measures: Sequence[Measure] = document.measures
        chosen: list[int] = sorted(
            measures.index(
                expect_entity(entities_by_id=entities_by_id, entity_id=measure_id, expected=Measure)
            )
            for measure_id in intent.measure_ids
        ) or [measures.index(clef.start.measure)]
        if chosen != list(range(chosen[0], chosen[-1] + 1)):
            raise MutationRejectedError("The measures a clef is taken out of are contiguous.")

        if measures.index(clef.start.measure) not in chosen:
            raise MutationRejectedError("The measures a clef is taken out of hold the clef.")

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        requests: list[MutationRequest]
        if chosen[-1] + 1 < len(measures):
            boundary: Measure = measures[chosen[-1] + 1]
            continues: bool = (
                ContextIndex(document=document, geometry=geometry).region_of(context=clef).end
                > geometry.measure_span(measure=boundary).start
            )
        else:
            boundary = clef.start.measure
            continues = False

        if continues:
            requests = [
                UpdateContextStartRequest(target=clef, measure=boundary, position=MEASURE_START)
            ]
        else:
            requests = [DeleteRequest(target=clef)]

        return in_mode(document=document, staff=clef.staff, mode=intent.mode, requests=requests)


class DeleteOctaveTranspositionCompiler:
    """Compiles deleting an octave line into one delete request, under a pitch-preserving
    request when the notes it reached are to sound as before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: DeleteOctaveTranspositionIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.octave_id,),
        )
        octave: OctaveTransposition = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.octave_id,
            expected=OctaveTransposition,
        )

        return in_mode(
            document=document,
            staff=octave.staff,
            mode=intent.mode,
            requests=[DeleteRequest(target=octave)],
        )


class MoveContextStartCompiler:
    """Compiles moving where a context starts into one update request; a clef or an octave
    line moves under a pitch-preserving request when its notes are to sound as before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveContextStartIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.context_id, intent.measure_id),
        )
        context: Context = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.context_id,
            expected=Context,
        )
        refuse_initial_context(document=document, entity=context)

        return in_mode(
            document=document,
            staff=context.staff if isinstance(context, ClefChange | OctaveTransposition) else None,
            mode=intent.mode,
            requests=[
                UpdateContextStartRequest(
                    target=context,
                    measure=expect_entity(
                        entities_by_id=entities_by_id,
                        entity_id=intent.measure_id,
                        expected=Measure,
                    ),
                    position=intent.position,
                )
            ],
        )


class MoveContextEndCompiler:
    """Compiles moving where a span context ends into one update request; an octave line moves
    under a pitch-preserving request when its notes are to sound as before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveContextEndIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.context_id, intent.measure_id),
        )
        context: SpanContext = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.context_id,
            expected=SpanContext,
        )

        return in_mode(
            document=document,
            staff=context.staff if isinstance(context, OctaveTransposition) else None,
            mode=intent.mode,
            requests=[
                UpdateContextEndRequest(
                    target=context,
                    measure=expect_entity(
                        entities_by_id=entities_by_id,
                        entity_id=intent.measure_id,
                        expected=Measure,
                    ),
                    position=intent.position,
                )
            ],
        )


class OpenContextEndCompiler:
    """Compiles making a span context last until the end of the score into one update request;
    an octave line moves under a pitch-preserving request when its notes are to sound as
    before."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: OpenContextEndIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.context_id,),
        )
        context: SpanContext = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.context_id,
            expected=SpanContext,
        )

        return in_mode(
            document=document,
            staff=context.staff if isinstance(context, OctaveTransposition) else None,
            mode=intent.mode,
            requests=[OpenContextEndRequest(target=context)],
        )
