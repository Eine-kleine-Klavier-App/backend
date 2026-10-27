from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CutAtBarlinesRequest(MutationRequest):
    """A request to cut every leaf starting in ``measures`` that crosses a barline at the
    barlines it crosses, the leaf itself kept as the first piece."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    measures: tuple[Measure, ...]
