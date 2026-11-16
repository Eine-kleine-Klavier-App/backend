from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateRhythmicGroupRequest,
    NoteContent,
    PlaceSpansRequest,
    RestContent,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError, SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class CreateTupletWithNoteCompiler:
    """Compiles a tuplet together with the note it starts with, as one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateTupletWithNoteIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
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

        accidental = intent.accidental
        if accidental is None:
            geometry = ScoreGeometry(document=document)
            try:
                accidental = ScorePitch(
                    document=document,
                    geometry=geometry,
                    contexts=ContextIndex(document=document, geometry=geometry),
                ).accidental_at(
                    staff=staff,
                    point=Point(
                        frame=geometry.of_measure(measure=measure), value=intent.position.value
                    ),
                    staff_step=intent.staff_step,
                    cell=SignCell.NOTE,
                )
            except (ValueError, PitchResolutionError) as error:
                raise MutationRejectedError(reason=str(error)) from error

        return [
            _tuplet_request(
                voice=voice,
                measure=measure,
                position=intent.position,
                written_size=intent.written_size,
                occupied_size=intent.occupied_size,
            ),
            PlaceSpansRequest(
                voice=voice,
                measure=measure,
                position=intent.position,
                written_length=intent.written_value.fraction,
                content=NoteContent(
                    staff=staff,
                    staff_step=intent.staff_step,
                    accidental=accidental,
                    fingering=intent.fingering,
                ),
            ),
        ]


class CreateTupletWithRestCompiler:
    """Compiles a tuplet together with the rest it starts with, as one gesture."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateTupletWithRestIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
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

        return [
            _tuplet_request(
                voice=voice,
                measure=measure,
                position=intent.position,
                written_size=intent.written_size,
                occupied_size=intent.occupied_size,
            ),
            PlaceSpansRequest(
                voice=voice,
                measure=measure,
                position=intent.position,
                written_length=intent.written_value.fraction,
                content=RestContent(staff=staff),
            ),
        ]


def _tuplet_request(
    *,
    voice: Voice,
    measure: Measure,
    position: MeasurePosition,
    written_size: RhythmicSize,
    occupied_size: RhythmicSize,
) -> CreateRhythmicGroupRequest:
    """The request creating the tuplet, addressed from its voice: its analyzer locates it
    on the live document. Its first element is placed right after, where the new tuplet
    is the deepest scope at its start; the fill tiles the rest of it at the gesture
    boundary.
    """
    return CreateRhythmicGroupRequest(
        voice=voice,
        measure=measure,
        position=position,
        written_size=written_size,
        occupied_size=occupied_size,
    )
