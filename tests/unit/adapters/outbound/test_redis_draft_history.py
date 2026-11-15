from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from piano_app.adapters.outbound.redis.draft_history import RedisDraftHistory
from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.ports.score import (
    DraftStoreNotFoundError,
    VersionedDraftDocument,
)
from piano_app.domain.score.document import ScoreDocument


def _missing_draft() -> VersionedDraftDocument:
    return VersionedDraftDocument.create(
        draft_id="missing",
        title="Missing",
        author_id="author",
        ref_score_id=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        document=ScoreDocument.create(voices=[], staffs=[], measures=[]),
        version=0,
    )


@pytest.fixture
async def history() -> AsyncIterator[RedisDraftHistory]:
    client: Redis = cast(Redis, FakeRedis())
    draft_history = RedisDraftHistory(client=client, codec=ScoreDocumentCodec())
    try:
        yield draft_history
    finally:
        await draft_history.aclose()


@pytest.mark.unit
async def test_get_returns_none_for_missing_draft(history: RedisDraftHistory) -> None:
    assert await history.get(draft_id="missing") is None


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["commit", "undo", "redo"])
async def test_commands_raise_for_missing_draft(
    history: RedisDraftHistory,
    operation: str,
) -> None:
    with pytest.raises(DraftStoreNotFoundError):
        await getattr(history, operation)(draft=_missing_draft())


@pytest.mark.unit
async def test_delete_removes_snapshot_keys_and_author_index(history: RedisDraftHistory) -> None:
    document = ScoreDocument.create(voices=[], staffs=[], measures=[])
    first = await history.create(
        title="First", author_id="author", ref_score_id="saved", document=document
    )
    second = await history.create(
        title="Second", author_id="author", ref_score_id="saved", document=document
    )
    await history.commit(draft=first)
    await history.delete(draft_id=first.draft_id)
    await history.delete(draft_id=first.draft_id)
    assert await history.get(draft_id=first.draft_id) is None
    assert [meta.draft_id for meta in await history.list_by_author(author_id="author")] == [
        second.draft_id
    ]
    with pytest.raises(DraftStoreNotFoundError):
        await history.commit(draft=first)


@pytest.mark.unit
async def test_cache_deletion_blocks_late_restoration_in_another_instance() -> None:
    from piano_app.adapters.outbound.redis.draft_cache import RedisDraftCache
    from piano_app.adapters.outbound.shared.draft_snapshot import DraftSnapshot

    client = cast(Redis, FakeRedis())
    cache = RedisDraftCache(client=client, codec=ScoreDocumentCodec())
    snapshot = DraftSnapshot.create(
        draft_id="deleted",
        title="Draft",
        author_id="author",
        ref_score_id="saved",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        revisions=[ScoreDocument.create(voices=[], staffs=[], measures=[])],
        cursor=0,
        version=0,
    )
    try:
        await cache.hydrate(snapshot=snapshot)
        await cache.delete(draft_id=snapshot.draft_id)
        other_instance = RedisDraftCache(client=client, codec=ScoreDocumentCodec())
        await other_instance.hydrate(snapshot=snapshot)
        assert await other_instance.get(draft_id=snapshot.draft_id) is None
        assert (
            await client.exists(
                "draft:deleted:revisions", "draft:deleted:state", "draft:deleted:meta"
            )
            == 0
        )
        assert not await client.sismember("drafts:author", "deleted")
        assert await client.get("draft:deleted:deleted") == b"1"
    finally:
        await cache.aclose()


@pytest.mark.unit
async def test_cold_only_deletion_blocks_restore_even_when_cache_is_already_empty() -> None:
    from piano_app.adapters.outbound.redis.draft_cache import RedisDraftCache
    from piano_app.adapters.outbound.shared.draft_snapshot import DraftSnapshot

    client = cast(Redis, FakeRedis())
    cache = RedisDraftCache(client=client, codec=ScoreDocumentCodec())
    snapshot = DraftSnapshot.create(
        draft_id="cold",
        title="Draft",
        author_id="author",
        ref_score_id=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        revisions=[ScoreDocument.create(voices=[], staffs=[], measures=[])],
        cursor=0,
        version=0,
    )
    try:
        await cache.delete(draft_id="cold")
        await cache.hydrate(snapshot=snapshot)
        assert await cache.get(draft_id="cold") is None
    finally:
        await cache.aclose()
