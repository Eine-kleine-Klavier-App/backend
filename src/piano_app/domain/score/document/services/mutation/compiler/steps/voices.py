from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

from .resolution import expect_entity


def expect_voices(
    *,
    entities_by_id: dict[str, ScoreEntity],
    voice_ids: Sequence[str],
    mark: str,
) -> tuple[Voice, ...]:
    """The resolved voices a mark is made for, in the order given; a mark names at least one
    voice, each once, else a reject."""
    if not voice_ids or len(voice_ids) != len(set(voice_ids)):
        raise MutationRejectedError(f"A {mark} names at least one voice, each once.")

    return tuple(
        expect_entity(entities_by_id=entities_by_id, entity_id=voice_id, expected=Voice)
        for voice_id in voice_ids
    )
