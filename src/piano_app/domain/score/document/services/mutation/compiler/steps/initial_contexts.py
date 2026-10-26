from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    KeySignatureChange,
    TempoChange,
)
from piano_app.domain.score.document.models.structural import MEASURE_START
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def refuse_initial_context(*, document: ScoreDocument, entity: ScoreEntity) -> None:
    """Refuses the clef, key signature, tempo and dynamic at the very start of the score, to be
    deleted or moved by the user: every score keeps them there (initial-clef-invariant). Replacing
    one by setting a new one there is allowed, and the engine's own measure edits carry them."""
    if (
        isinstance(entity, ClefChange | KeySignatureChange | TempoChange | DynamicChange)
        and entity.start.measure is document.measures[0]
        and entity.start.position == MEASURE_START
    ):
        raise MutationRejectedError(
            "The clef, key signature, tempo and dynamic at the start of the score "
            "cannot be deleted or moved."
        )
