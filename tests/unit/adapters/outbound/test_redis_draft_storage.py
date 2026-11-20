from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from piano_app.adapters.outbound.redis.draft_storage import RedisDraftStorage
from piano_app.application.ports.score import (
    StoredDraft,
)

_RECORD: dict[str, Any] = {"music_revision": "r1", "tables": {"notes": {"n1": {"step": 3}}}}


@pytest.fixture
async def storage() -> AsyncIterator[RedisDraftStorage]:
    redis_storage = RedisDraftStorage(client=cast(Redis, FakeRedis()))
    try:
        yield redis_storage
    finally:
        await redis_storage.aclose()


async def _created(storage: RedisDraftStorage, *, ref_score_id: str | None = None) -> StoredDraft:
    return await storage.create(
        title="Draft", author_id="author", ref_score_id=ref_score_id, record=_RECORD
    )


@pytest.mark.unit
async def test_hydrate_puts_back_a_draft_the_tier_lost(storage: RedisDraftStorage) -> None:
    created = await _created(storage)
    await storage.delete(draft_id=created.meta.draft_id)

    await storage.hydrate(draft=created)

    assert await storage.get(draft_id=created.meta.draft_id) == created


@pytest.mark.unit
async def test_hydrate_leaves_a_draft_the_tier_holds_as_it_is(storage: RedisDraftStorage) -> None:
    created = await _created(storage)
    newer = replace(created, version=1)
    await storage.put(draft=newer, expected_version=0)

    await storage.hydrate(draft=created)

    assert await storage.get(draft_id=created.meta.draft_id) == newer


@pytest.mark.unit
async def test_a_deleted_draft_is_not_brought_back_when_the_tier_remembers_deletions() -> None:
    remembering = RedisDraftStorage(client=cast(Redis, FakeRedis()), remember_deleted=True)
    try:
        created = await _created(remembering)
        await remembering.delete(draft_id=created.meta.draft_id)

        await remembering.hydrate(draft=created)

        assert await remembering.get(draft_id=created.meta.draft_id) is None
    finally:
        await remembering.aclose()
