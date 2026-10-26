from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.compiler.intents import InsertNoteIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    NoteContent,
    PlaceSpansRequest,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError, SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class InsertNoteCompiler:
    """Compiles a note insert into one request: its spans are placed — cut at the barlines
    and tied, joined or written over — and whatever they meet goes with them.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: InsertNoteIntent,
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
            # the pitch and the fingering go on every piece; showing them only on the
            # first is a display concern
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
