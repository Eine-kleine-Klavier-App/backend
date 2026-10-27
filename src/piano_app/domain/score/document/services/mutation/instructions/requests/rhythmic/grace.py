from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
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
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGraceGroupRequest(CreateMutationRequest[GraceGroup]):
    """A request to create the group of grace notes before or after a leaf's note, which has none
    yet at that place."""

    axis: ClassVar[Axis | None] = Axis.SPANS
    creates: ClassVar[type[ScoreEntity]] = GraceGroup

    leaf: LeafRhythmicContainer
    grace_type: GraceType
    placement: GracePlacement


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGraceItemRequest(CreateMutationRequest[GraceItem]):
    """A request to add a grace item, written as ``rhythmic_value``, to a group at ``index`` (the
    end when none); the time the group's notes take must still leave the note they belong to some
    of its own."""

    axis: ClassVar[Axis | None] = Axis.SPANS
    creates: ClassVar[type[ScoreEntity]] = GraceItem

    group: GraceGroup
    rhythmic_value: DottedRhythmicValue
    index: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateGraceTypeRequest(UpdateMutationRequest[GraceGroup]):
    """A request to set the kind of a group of grace notes; the time its notes then take must
    still leave the note they belong to some of its own."""

    axis: ClassVar[Axis | None] = Axis.SPANS

    grace_type: GraceType


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateGraceValueRequest(UpdateMutationRequest[GraceItem]):
    """A request to write a grace item as ``rhythmic_value``; the time its group's notes then take
    must still leave the note they belong to some of its own."""

    axis: ClassVar[Axis | None] = Axis.SPANS

    rhythmic_value: DottedRhythmicValue
