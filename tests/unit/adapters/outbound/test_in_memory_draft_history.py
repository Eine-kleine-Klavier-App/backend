from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.ports.score import (
    DraftStoreNotFoundError,
    VersionedDraftDocument,
)
from piano_app.application.ports.score.draft_store import DraftMeta
from piano_app.domain.score.document import ScoreDocument


class _Clock:
    def __init__(self, *values: datetime) -> None:
        self._values: Iterator[datetime] = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


def _document() -> ScoreDocument:
    return ScoreDocument.create(voices=[], staffs=[], measures=[])


def _missing_draft() -> VersionedDraftDocument:
    return VersionedDraftDocument.create(
        draft_id="missing",
        title="Missing",
        author_id="author",
        ref_score_id=None,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        document=_document(),
        version=0,
    )


@pytest.mark.unit
async def test_get_returns_none_for_missing_draft() -> None:
    history = InMemoryDraftHistory()

    assert await history.get(draft_id="missing") is None


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["commit", "undo", "redo"])
async def test_commands_raise_for_missing_draft(operation: str) -> None:
    history = InMemoryDraftHistory()

    with pytest.raises(DraftStoreNotFoundError):
        await getattr(history, operation)(draft=_missing_draft())


@pytest.mark.unit
async def test_create_returns_versioned_document_with_metadata() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    history = InMemoryDraftHistory(clock=_Clock(created_at))
    document = _document()

    created = await history.create(
        title="Draft title",
        author_id="author",
        ref_score_id="score",
        document=document,
    )

    assert created.meta == DraftMeta(
        draft_id=created.meta.draft_id,
        title="Draft title",
        author_id="author",
        ref_score_id="score",
        updated_at=created_at,
    )
    assert created.document is not document
    assert created.version == 0


@pytest.mark.unit
async def test_list_by_author_returns_metadata_newest_first() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    history = InMemoryDraftHistory(
        clock=_Clock(
            started_at,
            started_at + timedelta(seconds=1),
            started_at + timedelta(seconds=2),
        )
    )
    older = await history.create(
        title="Older",
        author_id="author",
        ref_score_id=None,
        document=_document(),
    )
    await history.create(
        title="Someone else's",
        author_id="other-author",
        ref_score_id=None,
        document=_document(),
    )
    newer = await history.create(
        title="Newer",
        author_id="author",
        ref_score_id=None,
        document=_document(),
    )

    assert await history.list_by_author(author_id="author") == [newer.meta, older.meta]
    assert await history.list_by_author(author_id="missing") == []


@pytest.mark.unit
async def test_updated_at_changes_only_when_history_changes() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    committed_at = started_at + timedelta(seconds=1)
    undone_at = started_at + timedelta(seconds=2)
    redone_at = started_at + timedelta(seconds=3)
    history = InMemoryDraftHistory(clock=_Clock(started_at, committed_at, undone_at, redone_at))
    created = await history.create(
        title="Draft",
        author_id="author",
        ref_score_id=None,
        document=_document(),
    )

    assert await history.undo(draft=created) is False
    assert await history.redo(draft=created) is False
    unchanged = await history.get(draft_id=created.meta.draft_id)
    assert unchanged is not None
    assert unchanged.meta.updated_at == started_at

    await history.commit(draft=created)
    committed = await history.get(draft_id=created.meta.draft_id)
    assert committed is not None
    assert committed.meta.updated_at == committed_at

    assert await history.undo(draft=committed) is True
    undone = await history.get(draft_id=created.meta.draft_id)
    assert undone is not None
    assert undone.meta.updated_at == undone_at

    assert await history.redo(draft=undone) is True
    redone = await history.get(draft_id=created.meta.draft_id)
    assert redone is not None
    assert redone.meta.updated_at == redone_at
