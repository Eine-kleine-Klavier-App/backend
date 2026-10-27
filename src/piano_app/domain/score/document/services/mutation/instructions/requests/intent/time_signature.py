from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeTimeSignatureRequest(MutationRequest):
    """A request to give exactly the selected ``measures`` of ``document`` — contiguous,
    in any order — ``time_signature``: everything in them keeps its time from the
    selection's start, only the barlines move."""

    axis: ClassVar[Axis | None] = Axis.INTENT

    document: ScoreDocument
    measures: tuple[Measure, ...]
    time_signature: RhythmicSize
