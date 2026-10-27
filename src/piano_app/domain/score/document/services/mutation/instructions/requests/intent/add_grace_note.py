from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    GracePlacement,
    GraceType,
)
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AddGraceNoteRequest(MutationRequest):
    """A request to add a grace note, written as ``written_value``, to the group before or after a
    leaf's note, making the group if it has none: the group, its item, the item's carrier and the
    note, in that order. It stands after the grace item ``after`` of that group, first when none."""

    axis: ClassVar[Axis | None] = Axis.INTENT

    leaf: LeafRhythmicContainer
    placement: GracePlacement
    grace_type: GraceType
    written_value: DottedRhythmicValue
    staff: Staff
    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE
    after: GraceItem | None = None
