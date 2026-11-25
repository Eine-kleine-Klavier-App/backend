from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    DeleteContextAction,
    UpdateContextEndAction,
    UpdateContextStartAction,
)


class DeleteContextHandler:
    """Detaches a context from its anchor(s)."""

    def handle(
        self,
        *,
        action: DeleteContextAction,
        sink: MutationSink,
    ) -> None:
        context: Context = action.target
        context.detach(sink=sink)
        return None


class UpdateContextStartHandler:
    """Moves a context's start to another anchor."""

    def handle(
        self,
        *,
        action: UpdateContextStartAction,
        sink: MutationSink,
    ) -> None:
        context: Context = action.target
        context.set_start(start=action.start, sink=sink)
        return None


class UpdateContextEndHandler:
    """Moves a span context's end to another anchor."""

    def handle(
        self,
        *,
        action: UpdateContextEndAction,
        sink: MutationSink,
    ) -> None:
        context: SpanContext = action.target
        context.set_end(end=action.end, sink=sink)
        return None
