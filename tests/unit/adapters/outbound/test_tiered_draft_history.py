import asyncio
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
    return VersionedDraftDocument(
        draft_id="draft",
        document=_document(),
        version=0,
        author_id="author",
        ref_score_id=None,
    )


def _snapshot() -> DraftSnapshot:
    return DraftSnapshot.create(
        draft_id="draft",
        author_id="author",
        ref_score_id=None,
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
