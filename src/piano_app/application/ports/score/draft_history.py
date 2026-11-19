from dataclasses import dataclass
from typing import Protocol

from .document_codec import DocumentRecord
from .draft_storage import RecordChange
from .draft_store import DraftStore, VersionedDraftDocument


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordStep:
    """One step of a draft's record: the record it was made from, the change that turns that
    record into the new one, and the versions of the draft before and after it."""

    before: DocumentRecord
    change: RecordChange
    from_version: int
    to_version: int


class DraftHistory(DraftStore, Protocol):
    """An extension of the draft store that also supports interaction with
    the recorded history by adding new entries to it by committing drafts
    or undoing/redoing them.
    """

    async def undo(self, *, draft: VersionedDraftDocument) -> RecordStep | None:
        """Rolls back the most recent gesture.

        ``draft.version`` is the version the caller loaded. Raises
        ``DraftStoreVersionConflictError`` if the draft has changed since then.
        Returns None if there is nothing to undo, else the step it wrote.
        """
        ...

    async def redo(self, *, draft: VersionedDraftDocument) -> RecordStep | None:
        """Reapplies the most recently undone gesture.

        ``draft.version`` is the version the caller loaded. Raises
        ``DraftStoreVersionConflictError`` if the draft has changed since then.
        Returns None if there is nothing to redo, else the step it wrote.
        """
        ...

    async def commit(self, *, draft: VersionedDraftDocument) -> RecordStep:
        """Commits a gesture if ``draft.version`` is still current and returns the step it wrote.

        Raises ``DraftStoreVersionConflictError`` if the draft has changed since it was loaded.
        """
        ...
