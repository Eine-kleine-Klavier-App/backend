from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateLeafAction(CreateMutationAction[LeafRhythmicContainer]):
    """Creates a leaf rhythmic container under a parent, at an anchor."""

    parent: RhythmicContainerParent
    anchor: TemporalAnchor
    size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteLeafAction(DeleteMutationAction[LeafRhythmicContainer]):
    """Deletes a leaf rhythmic container."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateLeafSizeAction(UpdateMutationAction[LeafRhythmicContainer]):
    """Resizes a leaf rhythmic container in place."""

    size: RhythmicSize
