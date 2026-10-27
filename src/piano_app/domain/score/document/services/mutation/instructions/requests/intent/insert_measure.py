from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class InsertMeasureRequest(MutationRequest):
    """A request to add a measure to ``document`` right before ``before``. Before the first
    measure it also carries the start-of-score clef and key signature over to the new one,
    which mixes contexts with rhythm, so it is an intent."""

    axis: ClassVar[Axis | None] = Axis.INTENT

    document: ScoreDocument
    before: Measure
