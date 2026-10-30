from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateGlissandoAction,
)


class CreateGlissandoHandler:
    """Creates a glissando between two notes."""

    def handle(
        self,
        *,
        action: CreateGlissandoAction,
        sink: MutationSink,
    ) -> Glissando:
        return Glissando.create(
            start_note=action.start_note,
            end_note=action.end_note,
            glissando_type=action.glissando_type,
            sink=sink,
        )
