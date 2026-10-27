from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTemporalAnchorRequest(CreateMutationRequest[TemporalAnchor]):
    """A request to create a temporal anchor at a measure position."""

    axis: ClassVar[Axis | None] = None
    creates: ClassVar[type[ScoreEntity]] = TemporalAnchor

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateTemporalAnchorRequest(UpdateMutationRequest[TemporalAnchor]):
    """A request to move an anchor to ``position`` in ``measure``, keeping it and
    everything starting or ending at it. Nothing else may stand there, and the move must
    keep the anchor's order on the timeline."""

    axis: ClassVar[Axis | None] = None

    measure: Measure
    position: MeasurePosition
