import asyncio
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fixtures.drafts import in_memory_history
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.draft.router import build_draft_router
from piano_app.application.use_cases.score.draft.service import DraftService
from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.material import Note

# GET /drafts/{draft}/contexts/{context}/coverage: the carriers and the notes a context is
# applied to, and a 404 for a context the draft does not have.


def _app_with_a_slur() -> tuple[TestClient, str, str, list[Note]]:
    document = score()
    notes: list[Note] = [note(document, Fraction(1) + Fraction(beat, 4)) for beat in range(4)]
    slur: Slur = Slur.create(
        start=anchor(document, Fraction(1)),
        end=anchor(document, Fraction(1) + Fraction(3, 4)),
        voice=document.voices[0],
    )
    storage = in_memory_history()
    draft = asyncio.run(
        storage.create(title="coverage", author_id="owner", ref_score_id=None, document=document)
    )
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_draft_router(
            service=DraftService(storage=storage, score_uow_factory=Mock()),
            current_user=CurrentUser(service=auth),
        )
    )

    return TestClient(app), draft.draft_id, slur.id, notes


@pytest.mark.unit
def test_the_route_gives_the_carriers_and_notes_a_context_is_applied_to() -> None:
    client, draft_id, slur_id, notes = _app_with_a_slur()

    with client:
        response = client.get(
            f"/drafts/{draft_id}/contexts/{slur_id}/coverage",
            headers={"Authorization": "Bearer owner"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "carrier_ids": [item.note_carrier.id for item in notes[:3]],
        "note_ids": [item.id for item in notes[:3]],
    }


@pytest.mark.unit
def test_an_unknown_context_is_a_404() -> None:
    client, draft_id, _slur_id, _notes = _app_with_a_slur()

    with client:
        response = client.get(
            f"/drafts/{draft_id}/contexts/no-such-context/coverage",
            headers={"Authorization": "Bearer owner"},
        )

    assert response.status_code == 404, response.text
