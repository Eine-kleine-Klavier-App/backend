import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from piano_app.adapters.outbound.shared.draft_snapshot import DraftSnapshot
from piano_app.adapters.outbound.tiered_draft_history import TieredDraftHistory
from piano_app.application.ports.score import (
    DraftStoreNotFoundError,
    VersionedDraftDocument,
)
from piano_app.domain.score.document import ScoreDocument


def _document() -> ScoreDocument:
    return ScoreDocument.create(voices=[], staffs=[], measures=[])


def _draft() -> VersionedDraftDocument:
    return VersionedDraftDocument.create(
        draft_id="draft",
        title="Draft",
        author_id="author",
        ref_score_id=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        document=_document(),
        version=0,
    )


def _snapshot() -> DraftSnapshot:
    return DraftSnapshot.create(
        draft_id="draft",
        title="Draft",
        author_id="author",
        ref_score_id=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        revisions=[_document()],
        cursor=0,
        version=0,
    )


@pytest.mark.unit
async def test_get_returns_hot_draft_without_reading_cold() -> None:
    draft = _draft()
    cache = AsyncMock()
    cache.get.return_value = draft
    archive = AsyncMock()
    history = TieredDraftHistory(archive=archive, cache=cache)

    assert await history.get(draft_id=draft.draft_id) is draft
    archive.get_snapshot.assert_not_awaited()


@pytest.mark.unit
async def test_get_restores_cold_draft_into_hot_cache() -> None:
    draft = _draft()
    snapshot = _snapshot()
    cache = AsyncMock()
    cache.get.side_effect = [None, draft]
    archive = AsyncMock()
    archive.get_snapshot.return_value = snapshot
    history = TieredDraftHistory(archive=archive, cache=cache)

    assert await history.get(draft_id=draft.draft_id) is draft
    cache.hydrate.assert_awaited_once_with(snapshot=snapshot)


@pytest.mark.unit
async def test_get_returns_none_when_both_tiers_miss() -> None:
    cache = AsyncMock()
    cache.get.return_value = None
    archive = AsyncMock()
    archive.get_snapshot.return_value = None
    history = TieredDraftHistory(archive=archive, cache=cache)

    assert await history.get(draft_id="missing") is None
    cache.hydrate.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("operation", "success_result"),
    [("commit", None), ("undo", True), ("redo", True)],
)
async def test_command_restores_cold_draft_and_retries(
    operation: str,
    success_result: bool | None,
) -> None:
    draft = _draft()
    snapshot = _snapshot()
    cache = AsyncMock()
    getattr(cache, operation).side_effect = [
        DraftStoreNotFoundError(draft_id=draft.draft_id),
        success_result,
    ]
    cache.load_snapshot.return_value = snapshot
    archive = AsyncMock()
    archive.get_snapshot.return_value = snapshot
    history = TieredDraftHistory(archive=archive, cache=cache)

    result = await getattr(history, operation)(draft=draft)
    await history.aclose()

    assert result is success_result
    cache.hydrate.assert_awaited_once_with(snapshot=snapshot)
    assert getattr(cache, operation).await_count == 2


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["commit", "undo", "redo"])
async def test_command_raises_when_both_tiers_miss(operation: str) -> None:
    draft = _draft()
    cache = AsyncMock()
    getattr(cache, operation).side_effect = DraftStoreNotFoundError(draft_id=draft.draft_id)
    archive = AsyncMock()
    archive.get_snapshot.return_value = None
    history = TieredDraftHistory(archive=archive, cache=cache)

    with pytest.raises(DraftStoreNotFoundError):
        await getattr(history, operation)(draft=draft)


@pytest.mark.unit
async def test_get_does_not_hide_infrastructure_failure() -> None:
    cache = AsyncMock()
    cache.get.side_effect = RuntimeError("redis unavailable")
    history = TieredDraftHistory(archive=AsyncMock(), cache=cache)

    with pytest.raises(RuntimeError, match="redis unavailable"):
        await history.get(draft_id="draft")


@pytest.mark.unit
async def test_aclose_waits_for_archiving_without_closing_injected_cache() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def load_snapshot(*, draft_id: str) -> DraftSnapshot:
        started.set()
        await release.wait()
        return _snapshot()

    cache = AsyncMock()
    cache.commit.return_value = None
    cache.load_snapshot.side_effect = load_snapshot
    archive = AsyncMock()
    history = TieredDraftHistory(archive=archive, cache=cache)

    await history.commit(draft=_draft())
    await started.wait()
    closing = asyncio.create_task(history.aclose())
    await asyncio.sleep(0)

    assert not closing.done()
    release.set()
    await closing
    cache.aclose.assert_not_awaited()


@pytest.mark.unit
async def test_delete_removes_cold_before_hot() -> None:
    archive, cache = AsyncMock(), AsyncMock()
    operations: list[str] = []

    async def cold_delete(*, draft_id: str) -> None:
        assert draft_id == "draft"
        operations.append("cold")

    async def hot_delete(*, draft_id: str) -> None:
        assert draft_id == "draft"
        operations.append("hot")

    archive.delete.side_effect = cold_delete
    cache.delete.side_effect = hot_delete
    history = TieredDraftHistory(archive=archive, cache=cache)
    await history.delete(draft_id="draft")
    assert operations == ["cold", "hot"]


@pytest.mark.unit
async def test_failed_cold_delete_preserves_hot_copy() -> None:
    archive, cache = AsyncMock(), AsyncMock()
    archive.delete.side_effect = RuntimeError("archive unavailable")
    history = TieredDraftHistory(archive=archive, cache=cache)
    with pytest.raises(RuntimeError, match="archive unavailable"):
        await history.delete(draft_id="draft")
    cache.delete.assert_not_awaited()


@pytest.mark.unit
async def test_late_restore_cannot_resurrect_deleted_copy() -> None:
    from typing import cast

    from fakeredis.aioredis import FakeRedis
    from redis.asyncio import Redis

    from piano_app.adapters.outbound.redis.draft_cache import RedisDraftCache
    from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec

    entered, release = asyncio.Event(), asyncio.Event()
    archive = AsyncMock()

    async def held_snapshot(*, draft_id: str) -> DraftSnapshot:
        assert draft_id == "draft"
        entered.set()
        await release.wait()
        return _snapshot()

    archive.get_snapshot.side_effect = held_snapshot
    cache = RedisDraftCache(client=cast(Redis, FakeRedis()), codec=ScoreDocumentCodec())
    history = TieredDraftHistory(archive=archive, cache=cache)
    try:
        restoring = asyncio.create_task(history.get(draft_id="draft"))
        await entered.wait()
        await history.delete(draft_id="draft")
        release.set()
        assert await restoring is None
        assert await cache.get(draft_id="draft") is None
    finally:
        release.set()
        await cache.aclose()
