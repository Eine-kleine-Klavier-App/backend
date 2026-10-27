from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateLeafRequest(CreateMutationRequest[LeafRhythmicContainer]):
    """A request to create a leaf rhythmic container in a rhythmic scope at a measure
    position. The scope is decided by whoever issues it; the leaf never descends on its
    own, and its room must already be clear."""

    axis: ClassVar[Axis | None] = Axis.SPANS
    creates: ClassVar[type[ScoreEntity]] = LeafRhythmicContainer

    scope: RhythmicContainerParent
    measure: Measure
    position: MeasurePosition
    written_size: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateLeafSizeRequest(UpdateMutationRequest[LeafRhythmicContainer]):
    """A request to resize a leaf in place, keeping its carrier and everything on it. Its
    new room must already be clear."""

    axis: ClassVar[Axis | None] = Axis.SPANS

    written_size: RhythmicSize
