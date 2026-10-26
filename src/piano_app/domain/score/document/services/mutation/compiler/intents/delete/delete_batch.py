from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteBatchIntent(EditIntent):
    """Delete several entities at once — groups, leaves, note / rest carriers, single
    notes / rests, relations, contexts and measures — as one gesture."""

    entity_ids: tuple[str, ...]
