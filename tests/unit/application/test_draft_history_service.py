import pytest
from tests.fixtures.drafts import in_memory_history

from piano_app.application.ports.score import (
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    RecordStep,
    VersionedDraftDocument,
)
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure


def _document(*, measures: int = 2) -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=measures)


async def _created(history: DraftHistoryService) -> VersionedDraftDocument:
    return await history.create(
        title="Draft", author_id="author", ref_score_id=None, document=_document()
    )


async def _loaded(*, history: DraftHistoryService, draft_id: str) -> VersionedDraftDocument:
    loaded: VersionedDraftDocument | None = await history.get(draft_id=draft_id)
    assert loaded is not None
    return loaded


async def _append_measure(*, history: DraftHistoryService, draft_id: str) -> None:
    """One gesture: loads the draft, adds a measure and commits."""
    loaded: VersionedDraftDocument = await _loaded(history=history, draft_id=draft_id)
    loaded.document.append_measure(measure=Measure.create())
    await history.commit(draft=loaded)


async def _undone(*, history: DraftHistoryService, draft_id: str) -> RecordStep | None:
    return await history.undo(draft=await _loaded(history=history, draft_id=draft_id))


async def _redone(*, history: DraftHistoryService, draft_id: str) -> RecordStep | None:
    return await history.redo(draft=await _loaded(history=history, draft_id=draft_id))


async def _measure_count(*, history: DraftHistoryService, draft_id: str) -> int:
    return len((await _loaded(history=history, draft_id=draft_id)).document.measures)


@pytest.mark.unit
async def test_a_created_draft_is_read_back_as_it_was_made() -> None:
    history: DraftHistoryService = in_memory_history()

    draft: VersionedDraftDocument = await _created(history)
    loaded: VersionedDraftDocument = await _loaded(history=history, draft_id=draft.draft_id)

    assert draft.version == loaded.version == 0
    assert loaded.meta.title == "Draft"
    assert len(loaded.document.measures) == 2
    assert await history.get(draft_id="missing") is None


@pytest.mark.unit
async def test_a_commit_is_read_back_and_moves_the_version() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)

    await _append_measure(history=history, draft_id=draft.draft_id)

    loaded: VersionedDraftDocument = await _loaded(history=history, draft_id=draft.draft_id)
    assert (loaded.version, len(loaded.document.measures)) == (1, 3)


@pytest.mark.unit
async def test_undo_takes_a_gesture_back_and_redo_gives_it_again() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)
    await _append_measure(history=history, draft_id=draft.draft_id)

    assert await _undone(history=history, draft_id=draft.draft_id) is not None
    assert await _measure_count(history=history, draft_id=draft.draft_id) == 2

    assert await _redone(history=history, draft_id=draft.draft_id) is not None
    assert await _measure_count(history=history, draft_id=draft.draft_id) == 3


@pytest.mark.unit
async def test_nothing_to_undo_or_redo_is_not_an_error() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)

    assert await history.undo(draft=draft) is None
    assert await history.redo(draft=draft) is None
    assert (await _loaded(history=history, draft_id=draft.draft_id)).version == 0


@pytest.mark.unit
async def test_a_gesture_after_an_undo_cuts_off_what_was_left_to_redo() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)
    await _append_measure(history=history, draft_id=draft.draft_id)
    await _undone(history=history, draft_id=draft.draft_id)

    await _append_measure(history=history, draft_id=draft.draft_id)

    assert await _redone(history=history, draft_id=draft.draft_id) is None
    assert await _measure_count(history=history, draft_id=draft.draft_id) == 3


@pytest.mark.unit
async def test_the_history_keeps_the_latest_gestures_only() -> None:
    history: DraftHistoryService = in_memory_history(max_history_size=2)
    draft: VersionedDraftDocument = await _created(history)
    for _ in range(3):
        await _append_measure(history=history, draft_id=draft.draft_id)

    assert await _undone(history=history, draft_id=draft.draft_id) is not None
    assert await _undone(history=history, draft_id=draft.draft_id) is not None
    assert await _undone(history=history, draft_id=draft.draft_id) is None
    assert await _measure_count(history=history, draft_id=draft.draft_id) == 3


@pytest.mark.unit
async def test_a_write_based_on_an_old_version_is_refused() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)
    await _append_measure(history=history, draft_id=draft.draft_id)
    stale: VersionedDraftDocument = await _loaded(history=history, draft_id=draft.draft_id)
    await _append_measure(history=history, draft_id=draft.draft_id)

    with pytest.raises(DraftStoreVersionConflictError):
        await history.commit(draft=stale)

    with pytest.raises(DraftStoreVersionConflictError):
        await history.undo(draft=stale)


@pytest.mark.unit
async def test_a_deleted_draft_cannot_be_written() -> None:
    history: DraftHistoryService = in_memory_history()
    draft: VersionedDraftDocument = await _created(history)
    loaded: VersionedDraftDocument = await _loaded(history=history, draft_id=draft.draft_id)
    await history.delete(draft_id=draft.draft_id)

    assert await history.get(draft_id=draft.draft_id) is None
    with pytest.raises(DraftStoreNotFoundError):
        await history.commit(draft=loaded)


@pytest.mark.unit
async def test_a_history_of_no_gestures_is_refused() -> None:
    with pytest.raises(ValueError, match="max_history_size"):
        in_memory_history(max_history_size=0)
