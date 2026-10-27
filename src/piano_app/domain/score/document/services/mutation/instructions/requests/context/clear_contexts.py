from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClearContextsRequest(MutationRequest):
    """A request to clear every context out of ``measure`` before the measure is removed:
    what lies inside it goes, an end reaching into it moves out of it."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
