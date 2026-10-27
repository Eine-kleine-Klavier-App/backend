from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Voice
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRhythmicGroupRequest(CreateMutationRequest[GroupRhythmicContainer]):
    """A request to create an empty rhythmic group starting at ``position`` in
    ``measure`` of ``voice``, in the deepest scope holding that start.
    ``occupied_size`` is read in that scope's units, ``written_size`` is the group's own
    interior."""

    axis: ClassVar[Axis | None] = Axis.FRAMES
    creates: ClassVar[type[ScoreEntity]] = GroupRhythmicContainer

    voice: Voice
    measure: Measure
    position: MeasurePosition
    written_size: RhythmicSize
    occupied_size: RhythmicSize
