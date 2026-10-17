from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note, Rest
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicSize
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    Location,
    expect_entity,
    locate,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
    CreateRestRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateRhythmicGroupRequest,
)


class CreateTupletWithNoteCompiler:
    """Compiles a tuplet together with the note it starts with, as one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateTupletWithNoteIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.voice_id, intent.staff_id, intent.measure_id),
        )
        voice: Voice = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.voice_id,
            expected=Voice,
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )

        tuplet: CreateRhythmicGroupRequest = _tuplet_request(
            voice=voice,
            measure=measure,
            position=intent.position,
            written_size=intent.written_size,
            occupied_size=intent.occupied_size,
            first_value=intent.written_value,
        )

        return [
            tuplet,
            CreateNoteRequest(
                scope=tuplet.out,
                staff=staff,
                measure=measure,
                position=intent.position,
                written_value=intent.written_value,
                staff_step=intent.staff_step,
                accidental=intent.accidental,
                fingering=intent.fingering,
                out=ResultRef[Note](),
            ),
        ]


class CreateTupletWithRestCompiler:
    """Compiles a tuplet together with the rest it starts with, as one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateTupletWithRestIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.voice_id, intent.staff_id, intent.measure_id),
        )
        voice: Voice = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.voice_id,
            expected=Voice,
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.staff_id,
            expected=Staff,
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )

        tuplet: CreateRhythmicGroupRequest = _tuplet_request(
            voice=voice,
            measure=measure,
            position=intent.position,
            written_size=intent.written_size,
            occupied_size=intent.occupied_size,
            first_value=intent.written_value,
        )

        return [
            tuplet,
            CreateRestRequest(
                scope=tuplet.out,
                staff=staff,
                measure=measure,
                position=intent.position,
                written_value=intent.written_value,
                out=ResultRef[Rest](),
            ),
        ]


def _tuplet_request(
    *,
    voice: Voice,
    measure: Measure,
    position: MeasurePosition,
    written_size: RhythmicSize,
    occupied_size: RhythmicSize,
    first_value: DottedRhythmicValue,
) -> CreateRhythmicGroupRequest:
    """The request creating the tuplet, located like a note — in the innermost scope
    holding its start, refused when it does not fit there — and never cut at a barline,
    since a group spans barlines on its own. Its first element is created into it right
    after, by the ref; the fill tiles the rest of it at the gesture boundary.
    """
    # what the tuplet takes is read in the scope it lands in
    location: Location = locate(
        voice=voice,
        measure=measure,
        position=position,
        length=occupied_size.fraction,
    )

    # the first element sounds its written value scaled by the tuplet; a barline inside it
    # would need slicing within a group that does not exist yet
    first: Span = Span(
        frame=location.span.frame,
        start=location.span.start,
        length=first_value.fraction * occupied_size.fraction / written_size.fraction,
    )
    geometry: ScoreGeometry = ScoreGeometry(origin=measure)
    if len(geometry.slice_by_measures(span=first)) > 1:
        raise MutationRejectedError("A tuplet's first element may not cross a barline yet.")

    return CreateRhythmicGroupRequest(
        scope=location.scope,
        measure=measure,
        position=position,
        written_size=written_size,
        occupied_size=occupied_size,
        out=ResultRef[GroupRhythmicContainer](),
    )
