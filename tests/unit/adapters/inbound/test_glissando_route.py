import asyncio
from fractions import Fraction
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.domain.document_builders import note, score

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

_Q: Fraction = Fraction(1, 4)


def _client() -> tuple[TestClient, str, str, str]:
    document = score()
    first = note(document, Fraction(0), step=-2)
    second = note(document, _Q, step=3)
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="gliss", author_id="owner", ref_score_id=None, document=document)
    )
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_edit_router(
            service=ScoreEditService(
                engine=build_engine(), compiler=build_compiler(), history=storage
            ),
            current_user=CurrentUser(service=auth),
        )
    )
    return TestClient(app), draft.draft_id, first.id, second.id


def test_the_glissando_route_joins_two_notes_and_the_view_shows_it() -> None:
    client, draft_id, start_id, end_id = _client()
    headers = {"Authorization": "Bearer owner"}

    response = client.post(
        f"/drafts/{draft_id}/edit/glissandos",
        headers=headers,
        json={"start_note_id": start_id, "end_note_id": end_id, "glissando_type": "wavy"},
    )

    assert response.status_code == 200, response.text
    (relation,) = [r for r in response.json()["document"]["relations"] if r["kind"] == "glissando"]
    assert relation["start_note_id"] == start_id and relation["end_note_id"] == end_id
    assert relation["glissando_type"] == "wavy"

    again = client.post(
        f"/drafts/{draft_id}/edit/glissandos",
        headers=headers,
        json={"start_note_id": start_id, "end_note_id": end_id},
    )
    assert again.status_code == 422, again.text
    assert "already starts another glissando" in again.text
