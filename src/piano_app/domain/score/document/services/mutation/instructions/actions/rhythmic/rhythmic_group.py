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
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRhythmicGroupAction(CreateMutationAction[GroupRhythmicContainer]):
    """Creates an empty rhythmic group at its anchor, inside its parent scope."""

    parent: Bound[RhythmicContainerParent]
    anchor: Bound[TemporalAnchor]
    written_size: RhythmicSize
    occupied_size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteRhythmicGroupAction(DeleteMutationAction[GroupRhythmicContainer]):
    """Deletes a rhythmic group container."""
