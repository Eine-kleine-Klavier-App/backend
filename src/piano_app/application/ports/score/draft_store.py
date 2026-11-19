from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from piano_app.domain.score.document import ScoreDocument

from .draft_storage import DraftMeta, StoredDraft


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionedDraftDocument:
    """A score document paired with the stored draft it was loaded from."""

    stored: StoredDraft
    document: ScoreDocument

    @property
    def meta(self) -> DraftMeta:
        return self.stored.meta

    @property
    def version(self) -> int:
        return self.stored.version

    @property
    def draft_id(self) -> str:
        return self.stored.meta.draft_id


class DraftStore(Protocol):
    """Holds the transient working copy (draft) of each editing session, keyed by
    draft id.

    Drafts are either branches from existing scores or a completely new score
    branched from an empty document.
    """

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        document: ScoreDocument,
    ) -> VersionedDraftDocument:
        """Creates initial draft with a fresh document."""
        ...

    async def delete(self, *, draft_id: str) -> None:
        """Removes a working copy and its history; a missing copy is a no-op."""
        ...

    async def get(self, *, draft_id: str) -> VersionedDraftDocument | None:
        """Returns ``None`` if ``draft_id`` has no working copy."""
        ...

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        """Returns all drafts created by ``author_id``, the latest updated first."""
        ...
