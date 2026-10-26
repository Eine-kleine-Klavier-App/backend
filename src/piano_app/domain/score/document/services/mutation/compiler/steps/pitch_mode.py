from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.services.mutation.compiler.intents import PitchEditMode
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    PreservePitchRequest,
)


def in_mode(
    *,
    document: ScoreDocument,
    staff: Staff | None,
    requests: Sequence[MutationRequest],
    mode: PitchEditMode,
) -> Sequence[MutationRequest]:
    """The requests of an edit that may change what the notes of ``staff`` sound like, as
    ``mode`` wants: kept as they are for step-preserving, where the notes stay put, and under
    a pitch-preserving request otherwise. With no ``staff`` the edit reaches no notes."""
    if staff is None or mode is PitchEditMode.PRESERVE_STEP:
        return requests

    return [PreservePitchRequest(document=document, staffs=(staff,), requests=tuple(requests))]
