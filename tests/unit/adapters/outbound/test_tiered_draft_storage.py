from dataclasses import replace
from datetime import UTC, datetime

import pytest

from piano_app.adapters.outbound.in_memory.draft_storage import InMemoryDraftStorage
from piano_app.adapters.outbound.tiered_draft_storage import TieredDraftStorage
from piano_app.application.ports.score import (
    DraftMeta,
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    StoredDraft,
)

_RECORD = {"tables": {}}


class _Hot(InMemoryDraftStorage):
    async def hydrate(self, *, draft: StoredDraft) -> None:
        if await self.get(draft_id=draft.meta.draft_id) is None:
            self._drafts[draft.meta.draft_id] = draft

    def lose(self, *, draft_id: str) -> None:
        del self._drafts[draft_id]


class _Cold(InMemoryDraftStorage):
    def __init__(self) -> None:
        super().__init__()
        self.failing: bool = False

    async def archive(self, *, draft: StoredDraft) -> None:
        if self.failing:
            raise RuntimeError("cold is down")

        stored: StoredDraft | None = self._drafts.get(draft.meta.draft_id)
        if stored is None or stored.version < draft.version:
            self._drafts[draft.meta.draft_id] = draft


def _tiers() -> tuple[TieredDraftStorage, _Hot, _Cold]:
    hot, cold = _Hot(), _Cold()
    return TieredDraftStorage(archive=cold, cache=hot), hot, cold


async def _created(storage: TieredDraftStorage) -> StoredDraft:
    return await storage.create(
        title="Draft", author_id="author", ref_score_id=None, record=_RECORD
    )


@pytest.mark.unit
async def test_a_created_draft_is_in_both_tiers() -> None:
    storage, hot, cold = _tiers()

    created = await _created(storage)

    assert await hot.get(draft_id=created.meta.draft_id) == created
    assert await cold.get(draft_id=created.meta.draft_id) == created


@pytest.mark.unit
async def test_a_put_lands_in_hot_and_reaches_cold_in_the_background() -> None:
    storage, hot, cold = _tiers()
    created = await _created(storage)
    newer = replace(created, version=1)

    await storage.put(draft=newer, expected_version=0)
    await storage.aclose()

    assert await hot.get(draft_id=created.meta.draft_id) == newer
    assert await cold.get(draft_id=created.meta.draft_id) == newer


@pytest.mark.unit
async def test_a_draft_hot_lost_is_read_back_from_cold() -> None:
    storage, hot, _ = _tiers()
    created = await _created(storage)
    hot.lose(draft_id=created.meta.draft_id)

    assert await storage.get(draft_id=created.meta.draft_id) == created
    assert await hot.get(draft_id=created.meta.draft_id) == created


@pytest.mark.unit
async def test_a_put_of_a_draft_hot_lost_restores_it_and_lands() -> None:
    storage, hot, _ = _tiers()
    created = await _created(storage)
    hot.lose(draft_id=created.meta.draft_id)
    newer = replace(created, version=1)

    await storage.put(draft=newer, expected_version=0)
    await storage.aclose()

    assert await hot.get(draft_id=created.meta.draft_id) == newer


@pytest.mark.unit
async def test_a_draft_neither_tier_holds_is_not_found() -> None:
    storage, _, _ = _tiers()
    unknown = StoredDraft(
        meta=DraftMeta(
            draft_id="unknown",
            title="Draft",
            author_id="author",
            ref_score_id=None,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        version=1,
        record=_RECORD,
        changes=(),
        cursor=0,
    )

    assert await storage.get(draft_id="unknown") is None
    with pytest.raises(DraftStoreNotFoundError):
        await storage.put(draft=unknown, expected_version=0)


@pytest.mark.unit
async def test_a_failed_archive_does_not_fail_the_write() -> None:
    storage, hot, cold = _tiers()
    created = await _created(storage)
    cold.failing = True
    newer = replace(created, version=1)

    await storage.put(draft=newer, expected_version=0)
    await storage.aclose()

    assert await hot.get(draft_id=created.meta.draft_id) == newer
    assert await cold.get(draft_id=created.meta.draft_id) == created


@pytest.mark.unit
async def test_a_write_cold_never_got_is_lost_when_hot_loses_the_draft() -> None:
    storage, hot, cold = _tiers()
    created = await _created(storage)
    cold.failing = True
    await storage.put(draft=replace(created, version=1), expected_version=0)
    await storage.aclose()
    hot.lose(draft_id=created.meta.draft_id)

    with pytest.raises(DraftStoreVersionConflictError):
        await storage.put(draft=replace(created, version=2), expected_version=1)


@pytest.mark.unit
async def test_delete_removes_the_draft_from_both_tiers() -> None:
    storage, hot, cold = _tiers()
    created = await _created(storage)

    await storage.delete(draft_id=created.meta.draft_id)

    assert await hot.get(draft_id=created.meta.draft_id) is None
    assert await cold.get(draft_id=created.meta.draft_id) is None
