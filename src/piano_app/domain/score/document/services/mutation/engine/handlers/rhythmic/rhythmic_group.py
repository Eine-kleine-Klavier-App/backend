from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateRhythmicGroupAction,
    DeleteRhythmicGroupAction,
)


class CreateRhythmicGroupHandler:
    """Creates an empty rhythmic group at its anchor, inside its parent scope (both
    resolved from the environment)."""

    def handle(
        self,
        *,
        action: CreateRhythmicGroupAction,
        resolve: ResolveBound,
        sink: MutationSink,
    ) -> GroupRhythmicContainer:
        anchor: TemporalAnchor = resolve(action.anchor)
        parent: RhythmicContainerParent = resolve(action.parent)

        group: GroupRhythmicContainer = GroupRhythmicContainer.create(
            parent=parent,
            anchor=anchor,
            written_size=action.written_size,
            occupied_size=action.occupied_size,
            sink=sink,
        )
        return group


class DeleteRhythmicGroupHandler:
    """Detaches a rhythmic group from its parent scope."""

    def handle(
        self,
        *,
        action: DeleteRhythmicGroupAction,
        resolve: ResolveBound,
        sink: MutationSink,
    ) -> None:
        group: GroupRhythmicContainer = action.target
        group.detach(sink=sink)
        return None
