import asyncio
import contextlib
from collections.abc import Sequence
from typing import Protocol

from piano_app.application.ports.score import (
    DocumentRecord,
    DraftMeta,
    DraftStoreNotFoundError,
    StoredDraft,
)


class DraftArchive(Protocol):
    """Cold-tier draft storage: a whole `StoredDraft` moves in and out of durable storage and
    nothing else is asked of it. `list_by_author` is the one read that never goes through hot
    (see `TieredDraftStorage.list_by_author`): cold is the only tier guaranteed to hold every
    draft, not just the currently-hot ones.

    `TieredDraftStorage`'s own dependency contract.
    """

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft: ...

    async def delete(self, *, draft_id: str) -> None: ...

    async def archive(self, *, draft: StoredDraft) -> None: ...

    async def get(self, *, draft_id: str) -> StoredDraft | None: ...

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]: ...


class DraftCache(Protocol):
    """Hot-tier draft storage: the fast store `TieredDraftStorage` reads and writes on the
    request path. `hydrate` puts back a draft the tier lost.

    `TieredDraftStorage`'s own dependency contract.
    """

    async def get(self, *, draft_id: str) -> StoredDraft | None: ...

    async def put(self, *, draft: StoredDraft, expected_version: int) -> None: ...

    async def delete(self, *, draft_id: str) -> None: ...

    async def hydrate(self, *, draft: StoredDraft) -> None: ...


class TieredDraftStorage:
    """Drafts in a fast cache, each write copied to a durable archive in the background.

    A write the archive did not get (it was down, or the process ended first) is lost if the
    cache then loses the draft: the next write finds the older archived version and is refused
    as a conflict."""

    def __init__(self, *, archive: DraftArchive, cache: DraftCache) -> None:
        self._hot: DraftCache = cache
        self._cold: DraftArchive = archive
        self._archive_tasks: set[asyncio.Task[None]] = set()

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft:
        draft: StoredDraft = await self._cold.create(
            title=title,
            author_id=author_id,
            ref_score_id=ref_score_id,
            record=record,
        )
        await self._hot.hydrate(draft=draft)

        return draft

    async def delete(self, *, draft_id: str) -> None:
        await self._cold.delete(draft_id=draft_id)
        await self._hot.delete(draft_id=draft_id)

    # cold only, no need for a fast cache for this operation
    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        return await self._cold.list_by_author(author_id=author_id)

    async def get(self, *, draft_id: str) -> StoredDraft | None:
        """Gets a draft from the hot tier, restoring from cold if necessary."""
        draft: StoredDraft | None = await self._hot.get(draft_id=draft_id)
        if draft is not None:
            return draft

        if not await self._restore(draft_id=draft_id):
            return None

        return await self._hot.get(draft_id=draft_id)

    async def put(self, *, draft: StoredDraft, expected_version: int) -> None:
        try:
            await self._hot.put(draft=draft, expected_version=expected_version)
        except DraftStoreNotFoundError:
            if not await self._restore(draft_id=draft.meta.draft_id):
                raise DraftStoreNotFoundError(draft_id=draft.meta.draft_id) from None

            await self._hot.put(draft=draft, expected_version=expected_version)

        task: asyncio.Task[None] = asyncio.create_task(self._archive(draft=draft))
        self._archive_tasks.add(task)
        task.add_done_callback(self._archive_tasks.discard)

    async def aclose(self) -> None:
        if self._archive_tasks:
            await asyncio.gather(*self._archive_tasks, return_exceptions=True)

    async def _restore(self, *, draft_id: str) -> bool:
        draft: StoredDraft | None = await self._cold.get(draft_id=draft_id)
        if draft is None:
            return False

        await self._hot.hydrate(draft=draft)
        return True

    async def _archive(self, *, draft: StoredDraft) -> None:
        # TODO log a failure here; the next write archives the newer version
        with contextlib.suppress(Exception):
            await self._cold.archive(draft=draft)
