from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRhythmicGroupAction(CreateMutationAction[GroupRhythmicContainer]):
    """Creates an empty rhythmic group at its anchor, inside its parent scope."""

    parent: RhythmicContainerParent
    anchor: TemporalAnchor
    written_size: RhythmicSize
    occupied_size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRhythmicGroupAction(DeleteMutationAction[GroupRhythmicContainer]):
    """Deletes a rhythmic group container."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitRhythmicGroupAction(CreateMutationAction[GroupRhythmicContainer]):
    """Splits a rhythmic group in two at an anchor in one step; produces the second part."""

    group: GroupRhythmicContainer
    anchor: TemporalAnchor
    first_written_size: RhythmicSize
    first_occupied_size: RhythmicSize
    second_written_size: RhythmicSize
    second_occupied_size: RhythmicSize
