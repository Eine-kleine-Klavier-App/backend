import asyncio
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.domain.document_builders import note, score

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine


@pytest.mark.parametrize(
    "bad", [None, "empty", "zero", "large", "bool", "float", "unknown", "carrier"]
)
def test_http_relative_group_shift_and_history(bad: str | None) -> None:
    document = score()
    a = note(document, Fraction(0), step=-2)
    b = note(document, Fraction(1, 4), step=2)
    build_engine().process(document=document, requests=[])
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="shift", author_id="owner", ref_score_id=None, document=document)
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=storage)
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_edit_router(service=service, current_user=CurrentUser(service=auth)))
    body = {"note_ids": [a.id, b.id], "delta": 1}
    if bad == "empty":
        body["note_ids"] = []
    elif bad == "zero":
        body["delta"] = 0
    elif bad == "large":
        body["delta"] = 2
    elif bad == "bool":
        body["delta"] = True
    elif bad == "float":
        body["delta"] = 1.0
    elif bad == "unknown":
        body["note_ids"] = [a.id, "missing"]
    elif bad == "carrier":
        body["note_ids"] = [a.note_carrier.id]
    with TestClient(app) as client:
        path = f"/drafts/{draft.draft_id}/edit/pitches/shift"
        response = client.post(path, headers={"Authorization": "Bearer owner"}, json=body)
        assert response.status_code == (422 if bad else 200), response.text
        if bad:
            current = asyncio.run(storage.get(draft_id=draft.draft_id))
            assert current is not None and current.version == 0
        else:
            steps = {
                item["id"]: item["staff_step"]
                for item in response.json()["document"]["items"]
                if item["kind"] == "note"
            }
            assert (steps[a.id], steps[b.id]) == (-1, 3)
            again = client.post(path, headers={"Authorization": "Bearer owner"}, json=body)
            assert again.status_code == 200
            steps = {
                item["id"]: item["staff_step"]
                for item in again.json()["document"]["items"]
                if item["kind"] == "note"
            }
            assert (steps[a.id], steps[b.id]) == (0, 4)
            asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
            # One Undo reverses the entire second command, not just its last note.
            current = asyncio.run(storage.get(draft_id=draft.draft_id))
            assert current is not None
            from piano_app.domain.score.document.models.material import NoteCarrier
            from piano_app.domain.score.document.services.helpers import iter_leaves

            found = {
                n.id: n.staff_step
                for voice in current.document.voices
                for leaf in iter_leaves(voice)
                if isinstance(leaf.carrier, NoteCarrier)
                for n in leaf.carrier.notes
            }
            assert (found[a.id], found[b.id]) == (-1, 3)
            asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
            asyncio.run(service.redo(draft_id=draft.draft_id, actor_id="owner"))
            current = asyncio.run(storage.get(draft_id=draft.draft_id))
            assert current is not None and current.version == 5


@pytest.mark.parametrize("delta", [-1, 1])
@pytest.mark.parametrize("blocked", [False, True])
def test_http_single_note_skips_unison_with_one_history_entry(delta, blocked):
    document = score()
    moving = note(document, Fraction(0), step=-2)
    for distance in range(1, 3 if blocked else 2):
        Note.create(
            note_carrier=moving.note_carrier,
            staff=moving.staff,
            staff_step=-2 + distance * delta,
            accidental=Accidental.NATURAL,
        )
    build_engine().process(document=document, requests=[])
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="skip unison", author_id="owner", ref_score_id=None, document=document)
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=storage)
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_edit_router(service=service, current_user=CurrentUser(service=auth)))
    with TestClient(app) as client:
        response = client.post(
            f"/drafts/{draft.draft_id}/edit/pitches/shift",
            headers={"Authorization": "Bearer owner"},
            json={"note_ids": [moving.id], "delta": delta},
        )
    assert response.status_code == (422 if blocked else 200), response.text
    current = asyncio.run(storage.get(draft_id=draft.draft_id))
    assert current is not None and current.version == (0 if blocked else 1)
    if not blocked:
        steps = {
            item["id"]: item["staff_step"]
            for item in response.json()["document"]["items"]
            if item["kind"] == "note"
        }
        assert steps[moving.id] == -2 + 2 * delta
        asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
        current = asyncio.run(storage.get(draft_id=draft.draft_id))
        assert current is not None
        from piano_app.domain.score.document.models.material import NoteCarrier
        from piano_app.domain.score.document.services.helpers import iter_leaves

        found = {
            n.id: n.staff_step
            for voice in current.document.voices
            for leaf in iter_leaves(voice)
            if isinstance(leaf.carrier, NoteCarrier)
            for n in leaf.carrier.notes
        }
        assert found[moving.id] == -2
        asyncio.run(service.redo(draft_id=draft.draft_id, actor_id="owner"))
        current = asyncio.run(storage.get(draft_id=draft.draft_id))
        assert current is not None and current.version == 3
