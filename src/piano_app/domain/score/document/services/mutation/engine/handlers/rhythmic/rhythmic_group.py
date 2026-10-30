from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateRhythmicGroupAction,
    DeleteRhythmicGroupAction,
    SplitRhythmicGroupAction,
)


class CreateRhythmicGroupHandler:
    """Creates an empty rhythmic group at its anchor, inside its parent scope."""

    def handle(
        self,
        *,
        action: CreateRhythmicGroupAction,
        sink: MutationSink,
    ) -> GroupRhythmicContainer:
        anchor: TemporalAnchor = action.anchor
        parent: RhythmicContainerParent = action.parent

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
        sink: MutationSink,
    ) -> None:
        group: GroupRhythmicContainer = action.target
        group.detach(sink=sink)
        return None


class SplitRhythmicGroupHandler:
    """Splits a rhythmic group in two at an anchor, in one model step."""

    def handle(
        self,
        *,
        action: SplitRhythmicGroupAction,
        sink: MutationSink,
    ) -> GroupRhythmicContainer:
        return action.group.split_at(
            anchor=action.anchor,
            first_written_size=action.first_written_size,
            first_occupied_size=action.first_occupied_size,
            second_written_size=action.second_written_size,
            second_occupied_size=action.second_occupied_size,
            sink=sink,
        )
