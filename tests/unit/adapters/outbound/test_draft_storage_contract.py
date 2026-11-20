"""What every draft storage does the same, run over each of them."""

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from piano_app.adapters.outbound.in_memory.draft_storage import InMemoryDraftStorage
from piano_app.adapters.outbound.redis.draft_storage import RedisDraftStorage
from piano_app.application.ports.score import (
    DraftStorage,
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    StoredDraft,
)

_RECORD: dict[str, Any] = {"music_revision": "r1", "tables": {"notes": {"n1": {"step": 3}}}}


@pytest.fixture(params=["memory", "redis"])
async def storage(request: pytest.FixtureRequest) -> AsyncIterator[DraftStorage]:
    if request.param == "memory":
        yield InMemoryDraftStorage()
        return

    redis_storage = RedisDraftStorage(client=cast(Redis, FakeRedis()))
    try:
        yield redis_storage
    finally:
        await redis_storage.aclose()


async def _created(storage: DraftStorage, *, ref_score_id: str | None = None) -> StoredDraft:
    return await storage.create(
        title="Draft", author_id="author", ref_score_id=ref_score_id, record=_RECORD
    )


@pytest.mark.unit
async def test_get_returns_none_for_a_missing_draft(storage: DraftStorage) -> None:
    assert await storage.get(draft_id="missing") is None


@pytest.mark.unit
@pytest.mark.parametrize("ref_score_id", [None, "saved"])
async def test_a_created_draft_is_read_back_as_it_was_made(
    storage: DraftStorage, ref_score_id: str | None
) -> None:
    created = await _created(storage, ref_score_id=ref_score_id)

    assert await storage.get(draft_id=created.meta.draft_id) == created
    assert (created.version, created.changes, created.cursor) == (0, (), 0)
    assert created.meta.ref_score_id == ref_score_id


@pytest.mark.unit
async def test_a_put_stores_the_record_the_changes_and_the_cursor(storage: DraftStorage) -> None:
    created = await _created(storage)
    change = {"tables": {"notes": {"n1": [{"step": 3}, {"step": 4}]}}}
    newer = replace(
        created,
        version=1,
        record={"music_revision": "r2", "tables": {"notes": {"n1": {"step": 4}}}},
        changes=(change,),
        cursor=1,
    )

    await storage.put(draft=newer, expected_version=0)

    loaded = await storage.get(draft_id=created.meta.draft_id)
    assert loaded is not None
    assert (loaded.version, loaded.record, loaded.changes, loaded.cursor) == (
        1,
        newer.record,
        (change,),
        1,
    )


@pytest.mark.unit
async def test_a_change_of_a_list_of_ids_is_read_back_as_it_was_stored(
    storage: DraftStorage,
) -> None:
    created = await _created(storage)
    change = {
        "fields": {
            "relation_ids": {"removed": [[72, "r72"], [78, "r78"]], "inserted": [[0, "new"]]},
            "measure_ids": {"removed": [], "inserted": []},
        }
    }
    newer = replace(created, version=1, record=_RECORD, changes=(change,), cursor=1)

    await storage.put(draft=newer, expected_version=0)

    assert (await storage.get(draft_id=created.meta.draft_id)) == newer


@pytest.mark.unit
async def test_a_put_on_another_version_is_refused_and_changes_nothing(
    storage: DraftStorage,
) -> None:
    created = await _created(storage)

    with pytest.raises(DraftStoreVersionConflictError):
        await storage.put(draft=replace(created, version=6), expected_version=5)

    assert await storage.get(draft_id=created.meta.draft_id) == created


@pytest.mark.unit
async def test_a_put_of_a_deleted_draft_is_refused(storage: DraftStorage) -> None:
    created = await _created(storage)
    await storage.delete(draft_id=created.meta.draft_id)

    with pytest.raises(DraftStoreNotFoundError):
        await storage.put(draft=replace(created, version=1), expected_version=0)


@pytest.mark.unit
async def test_delete_removes_the_draft_and_its_place_in_the_author_list(
    storage: DraftStorage,
) -> None:
    first = await _created(storage)
    second = await _created(storage)

    await storage.delete(draft_id=first.meta.draft_id)
    await storage.delete(draft_id=first.meta.draft_id)

    assert await storage.get(draft_id=first.meta.draft_id) is None
    listed = await storage.list_by_author(author_id="author")
    assert [meta.draft_id for meta in listed] == [second.meta.draft_id]


@pytest.mark.unit
async def test_drafts_are_listed_by_author_latest_first(storage: DraftStorage) -> None:
    first = await _created(storage)
    second = await _created(storage)
    await storage.create(title="Other", author_id="other", ref_score_id=None, record=_RECORD)

    listed = await storage.list_by_author(author_id="author")

    newest_first = sorted(
        [first.meta, second.meta], key=lambda meta: (meta.updated_at, meta.draft_id), reverse=True
    )
    assert listed == newest_first
