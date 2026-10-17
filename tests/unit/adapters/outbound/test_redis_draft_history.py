from collections.abc import AsyncIterator
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
    return VersionedDraftDocument(
        draft_id="missing",
        document=ScoreDocument.create(voices=[], staffs=[], measures=[]),
        version=0,
        author_id="author",
        ref_score_id=None,
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
