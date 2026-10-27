from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PreservePitchRequest(MutationRequest):
    """A request to run context edits that change what the notes of some staffs sound like, and
    then move every note of those staffs to the staff step that sounds as it did before."""

    axis: ClassVar[Axis | None] = Axis.INTENT

    document: ScoreDocument
    staffs: tuple[Staff, ...]
    requests: tuple[MutationRequest, ...]
