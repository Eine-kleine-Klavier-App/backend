from fractions import Fraction
from typing import cast
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.unit.application.test_score_visibility import _meta, _service
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.adapters.inbound.http import (
    CurrentUser,
    CurrentUserOptional,
    register_exception_handlers,
)
from piano_app.adapters.inbound.http.score.catalog.router import build_scores_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import ContextNotFoundError
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.catalog.service import ScoreCatalogService
from piano_app.application.use_cases.score.draft.service import ContextCoverage, DraftService
from piano_app.domain.score import Score
from piano_app.domain.score.document.models.context import SustainHold

# The use case reads a draft and answers with the ids of what a context is applied to.


async def test_the_coverage_of_a_context_is_its_carriers_and_notes_as_ids() -> None:
    document = score()
    notes = [note(document, Fraction(1) + Fraction(beat, 4)) for beat in range(4)]
    pedal = SustainHold.create(
        start=anchor(document, Fraction(1, 1) + Fraction(1, 4)),
        end=anchor(document, Fraction(1) + Fraction(3, 4)),
    )
    storage = InMemoryDraftHistory()
    draft = await storage.create(
        title="coverage", author_id="owner", ref_score_id=None, document=document
    )
    service = DraftService(storage=storage, score_uow_factory=Mock())

    coverage: ContextCoverage = await service.get_context_coverage(
        draft_id=draft.draft_id, viewer_id="owner", context_id=pedal.id
    )

    assert coverage.carrier_ids == tuple(item.note_carrier.id for item in notes[1:3])
    assert coverage.note_ids == tuple(item.id for item in notes[1:3])


async def test_a_context_the_draft_does_not_have_is_refused() -> None:
    storage = InMemoryDraftHistory()
    draft = await storage.create(
        title="coverage", author_id="owner", ref_score_id=None, document=score()
    )
    service = DraftService(storage=storage, score_uow_factory=Mock())

    with pytest.raises(ContextNotFoundError):
        await service.get_context_coverage(
            draft_id=draft.draft_id, viewer_id="owner", context_id="missing"
        )


@pytest.mark.parametrize(
    ("public", "actor", "allowed"),
    [(True, None, True), (False, "owner", True), (False, None, False), (False, "other", False)],
)
async def test_saved_context_coverage_http_matches_draft_and_is_read_only(
    public: bool, actor: str | None, allowed: bool
) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    for beat in range(4):
        note(document, Fraction(1) + Fraction(beat, 4))
    pedal = SustainHold.create(
        start=anchor(document, Fraction(5, 4)), end=anchor(document, Fraction(7, 4))
    )
    repository.get.return_value = Score(meta=_meta(public=public), document=document)
    service = ScoreCatalogService(score_uow_factory=lambda: uow)
    auth = cast(AuthService, MagicMock(spec=AuthService))
    current = CurrentUser(service=auth)
    optional = CurrentUserOptional(service=auth)
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_scores_router(service=service, current_user=current, current_user_optional=optional)
    )

    async def identity() -> str | None:
        return actor

    app.dependency_overrides[optional] = identity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/scores/score/contexts/{pedal.id}/coverage")
        assert response.status_code == (200 if allowed else 404)
        if allowed:
            storage = InMemoryDraftHistory()
            draft = await storage.create(
                title="copy", author_id="owner", ref_score_id="score", document=document
            )
            draft_service = DraftService(storage=storage, score_uow_factory=Mock())
            expected = await draft_service.get_context_coverage(
                draft_id=draft.draft_id, viewer_id="owner", context_id=pedal.id
            )
            assert response.json() == {
                "carrier_ids": list(expected.carrier_ids),
                "note_ids": list(expected.note_ids),
            }
            assert len(expected.note_ids) == 2
            assert (await client.get("/scores/score/contexts/missing/coverage")).status_code == 404
        else:
            assert "carrier_ids" not in response.json()
    uow.commit.assert_not_awaited()
    repository.create.assert_not_awaited()
    repository.update_content.assert_not_awaited()
