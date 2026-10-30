from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    DeleteTemporalAnchorAction,
    UpdateTemporalAnchorAction,
)


class CreateTemporalAnchorHandler:
    """Creates a temporal anchor in its measure."""

    def handle(
        self,
        *,
        action: CreateTemporalAnchorAction,
        sink: MutationSink,
    ) -> TemporalAnchor:
        anchor: TemporalAnchor = TemporalAnchor.create(
            position=action.position,
            measure=action.measure,
            sink=sink,
        )
        return anchor


class DeleteTemporalAnchorHandler:
    """Detaches a temporal anchor from its measure."""

    def handle(
        self,
        *,
        action: DeleteTemporalAnchorAction,
        sink: MutationSink,
    ) -> None:
        anchor: TemporalAnchor = action.target
        anchor.detach(sink=sink)
        return None


class UpdateTemporalAnchorHandler:
    """Moves a temporal anchor to another measure position."""

    def handle(
        self,
        *,
        action: UpdateTemporalAnchorAction,
        sink: MutationSink,
    ) -> None:
        anchor: TemporalAnchor = action.target
        anchor.move_to(measure=action.measure, position=action.position, sink=sink)
        return None
