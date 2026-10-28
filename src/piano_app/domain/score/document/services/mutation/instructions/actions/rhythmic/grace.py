from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGraceGroupAction(CreateMutationAction[GraceGroup]):
    """Creates a group of grace notes on a leaf."""

    leaf: LeafRhythmicContainer
    grace_type: GraceType
    placement: GracePlacement


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGraceItemAction(CreateMutationAction[GraceItem]):
    """Creates a grace item in a group, at ``index`` or at its end."""

    group: GraceGroup
    rhythmic_value: DottedRhythmicValue
    index: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteGraceGroupAction(DeleteMutationAction[GraceGroup]):
    """Deletes a group of grace notes."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteGraceItemAction(DeleteMutationAction[GraceItem]):
    """Deletes a grace item."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateGraceTypeAction(UpdateMutationAction[GraceGroup]):
    """Sets the kind of a group of grace notes."""

    grace_type: GraceType


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateGraceValueAction(UpdateMutationAction[GraceItem]):
    """Writes a grace item as another value."""

    rhythmic_value: DottedRhythmicValue
