from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitRhythmicGroupRequest(CreateMutationRequest[GroupRhythmicContainer]):
    """A request to split ``group`` in two at the barline at the start of ``measure``,
    which it crosses: the same ratio on both sides, each part written as its share of the
    room the group takes, the groups nested in it split the same way. It sends back the
    second part, the group it creates."""

    axis: ClassVar[Axis | None] = Axis.FRAMES
    creates: ClassVar[type[ScoreEntity]] = GroupRhythmicContainer

    group: GroupRhythmicContainer
    measure: Measure
