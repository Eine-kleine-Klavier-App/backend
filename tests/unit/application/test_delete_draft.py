from unittest.mock import AsyncMock, Mock

import pytest

from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import DraftNotFoundError
from piano_app.application.use_cases.score.draft.service import DraftService
from piano_app.domain.score.document import ScoreDocument


@pytest.mark.parametrize("ref_score_id", [None, "saved-score"])
async def test_owner_deletes_only_draft_without_touching_canon(ref_score_id: str | None) -> None:
    storage = InMemoryDraftHistory()
    draft = await storage.create(
        title="Draft",
        author_id="owner",
        ref_score_id=ref_score_id,
        document=ScoreDocument.create(voices=[], staffs=[], measures=[]),
    )
    factory = Mock()
    service = DraftService(storage=storage, score_uow_factory=factory)
    await service.delete_draft(draft_id=draft.draft_id, actor_id="owner")
    assert await storage.get(draft_id=draft.draft_id) is None
    factory.assert_not_called()
    with pytest.raises(DraftNotFoundError):
        await service.delete_draft(draft_id=draft.draft_id, actor_id="owner")


async def test_foreign_and_missing_copies_are_hidden() -> None:
    storage = InMemoryDraftHistory()
    draft = await storage.create(
        title="Private",
        author_id="owner",
        ref_score_id=None,
        document=ScoreDocument.create(voices=[], staffs=[], measures=[]),
    )
    service = DraftService(storage=storage, score_uow_factory=Mock())
    for draft_id in [draft.draft_id, "missing"]:
        with pytest.raises(DraftNotFoundError):
            await service.delete_draft(draft_id=draft_id, actor_id="other")
    assert await storage.get(draft_id=draft.draft_id) is not None


async def test_storage_failure_is_not_reported_as_success() -> None:
    storage = AsyncMock()
    storage.get.return_value.meta.author_id = "owner"
    storage.delete.side_effect = RuntimeError("storage unavailable")
    service = DraftService(storage=storage, score_uow_factory=Mock())
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await service.delete_draft(draft_id="draft", actor_id="owner")
