import asyncio
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fixtures.drafts import in_memory_history
from tests.unit.domain.scene import build_score, note_at, quarters

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

# An edit answers with the measures it changed and their sound, never the whole document.


@pytest.mark.unit
def test_an_edit_answers_with_the_measure_it_changed() -> None:
    score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    history = in_memory_history()
    draft = asyncio.run(
        history.create(title="sync", author_id="owner", ref_score_id=None, document=score.document)
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=history)
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_edit_router(service=service, current_user=CurrentUser(service=auth)))
    second = score.document.measures[1].id

    with TestClient(app) as client:
        path = f"/drafts/{draft.draft_id}/edit/fingerings"
        headers = {"Authorization": "Bearer owner"}
        body = {"note_id": note_at(score=score, at=Fraction(5, 4)).id, "fingering": 2}

        response = client.put(path, headers=headers, json=body)

    assert response.status_code == 200, response.text
    assert "document" not in response.json()
    sync = response.json()["sync"]
    assert (sync["from_version"], sync["to_version"]) == (0, 1)
    assert [share["measure"]["id"] for share in sync["measures"]] == [second]
    assert [sounds["measure_id"] for sounds in sync["sounds"]] == [second]
    assert sync["sound_error"] is None
