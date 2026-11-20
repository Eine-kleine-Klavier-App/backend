from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from piano_app.application.ports.score import (
    DocumentRecord,
    DraftMeta,
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    StoredDraft,
)


class InMemoryDraftStorage:
    """In-process draft storage keyed by draft id. A stored draft is never changed in place, so
    what ``get`` returns stays what it was when a later ``put`` replaces it."""

    def __init__(self) -> None:
        self._drafts: dict[str, StoredDraft] = {}

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft:
        draft_id: str = str(uuid4())
        draft: StoredDraft = StoredDraft(
            meta=DraftMeta(
                draft_id=draft_id,
                title=title,
                author_id=author_id,
                ref_score_id=ref_score_id,
                updated_at=datetime.now(UTC),
            ),
            version=0,
            record=record,
            changes=(),
            cursor=0,
        )
        self._drafts[draft_id] = draft

        return draft

    async def get(self, *, draft_id: str) -> StoredDraft | None:
        return self._drafts.get(draft_id)

    async def put(self, *, draft: StoredDraft, expected_version: int) -> None:
        draft_id: str = draft.meta.draft_id
        stored: StoredDraft | None = self._drafts.get(draft_id)
        if stored is None:
            raise DraftStoreNotFoundError(draft_id=draft_id)

        if stored.version != expected_version:
            raise DraftStoreVersionConflictError(draft_id=draft_id, version=expected_version)

        self._drafts[draft_id] = draft

    async def delete(self, *, draft_id: str) -> None:
        self._drafts.pop(draft_id, None)

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        matching: list[DraftMeta] = [
            draft.meta for draft in self._drafts.values() if draft.meta.author_id == author_id
        ]

        return sorted(matching, key=lambda meta: (meta.updated_at, meta.draft_id), reverse=True)
