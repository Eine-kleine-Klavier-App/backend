from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .document_codec import DocumentRecord


class DraftStoreNotFoundError(Exception):
    """Raised when a required draft disappears from the store."""

    def __init__(self, *, draft_id: str) -> None:
        super().__init__(f"No stored draft with id {draft_id!r}.")
        self.draft_id: str = draft_id


class DraftStoreVersionConflictError(Exception):
    """Raised when a write is based on an outdated stored draft version."""

    def __init__(self, *, draft_id: str, version: int | None) -> None:
        super().__init__(f"Stored draft {draft_id!r} is no longer at version {version!r}.")
        self.draft_id: str = draft_id
        self.version: int | None = version


@dataclass(frozen=True, slots=True, kw_only=True)
class DraftMeta:
    """Metadata about a draft."""

    draft_id: str
    title: str
    author_id: str
    ref_score_id: str | None
    updated_at: datetime


# What a gesture changed in a record, so that it can be taken back and applied again:
#
#     {"fields": {name: [before, after] | {"removed": [[index, id]], "inserted": [[index, id]]}},
#      "tables": {table: {row_id: [before_row, after_row]}}}
#
# A part that did not change is not written; a row that did not exist has ``None`` on that side. A
# field that is a list of ids is written as the ids that left it with their places and the ids that
# came in with theirs.
# See ``record_patch`` for how one is made and applied.
type RecordChange = dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredDraft:
    """A draft as the store keeps it: the current record, and the changes the history is made of.

    ``changes[i]`` turns the record before gesture ``i`` into the one after it. ``cursor`` is how
    many of them are applied: undo takes ``changes[cursor - 1]`` back, redo applies
    ``changes[cursor]``.
    """

    meta: DraftMeta
    version: int
    record: DocumentRecord
    changes: tuple[RecordChange, ...]
    cursor: int

    def __post_init__(self) -> None:
        if not 0 <= self.cursor <= len(self.changes):
            raise ValueError(f"cursor out of range: {self.cursor} (n={len(self.changes)})")


class DraftStorage(Protocol):
    """Keeps each draft as it is given: its record, its changes and its metadata. It knows
    nothing of what the history means; undo, redo and what a commit holds are the application's
    (``DraftHistoryService``). What it owns is that a write lands only on the version the writer
    read."""

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft:
        """Stores a new draft at version 0, with no changes."""
        ...

    async def get(self, *, draft_id: str) -> StoredDraft | None:
        """Returns ``None`` if ``draft_id`` has no working copy."""
        ...

    async def put(self, *, draft: StoredDraft, expected_version: int) -> None:
        """Replaces the stored draft with ``draft`` if the stored version is
        ``expected_version``.

        Raises ``DraftStoreVersionConflictError`` if it is another one and
        ``DraftStoreNotFoundError`` if the draft is gone.
        """
        ...

    async def delete(self, *, draft_id: str) -> None:
        """Removes a working copy; a missing copy is a no-op."""
        ...

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        """Returns all drafts created by ``author_id``, the latest updated first."""
        ...
