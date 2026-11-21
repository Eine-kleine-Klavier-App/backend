import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import EditPresentationRequest


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        {"left": float("inf"), "right": 0},
        {"left": 0},
        {"left": 0, "right": 0, "unknown": 1},
    ],
)
def test_invalid_offsets_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EditPresentationRequest.model_validate(
            {
                "changes": [
                    {
                        "kind": "endpoints",
                        "target": {"entity_id": "b", "reference": "body"},
                        "offsets": override,
                    }
                ]
            }
        )


@pytest.mark.unit
def test_http_edit_is_saved_and_reversible() -> None:
    import asyncio
    from fractions import Fraction
    from unittest.mock import Mock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.fixtures.drafts import in_memory_history
    from tests.fixtures.sync import ClientView
    from tests.unit.domain.scene import build_score, note, rest

    from piano_app.adapters.inbound.http.current_user import CurrentUser
    from piano_app.adapters.inbound.http.errors import register_exception_handlers
    from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
    from piano_app.application.use_cases.score.edit.service import ScoreEditService
    from piano_app.domain.score.document.models.notation import RhythmicValue
    from piano_app.domain.score.document.models.relations import Beam
    from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

    score = build_score(measure_count=1)
    members = []
    for i in range(8):
        leaf = (
            note(
                score=score,
                parent=score.voice,
                at=Fraction(i, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
                step=i,
            )
            if i < 4
            else rest(
                score=score,
                parent=score.voice,
                at=Fraction(i, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
            )
        )
        assert leaf.carrier is not None
        if i < 4:
            members.append(leaf.carrier)
    beam = Beam.create(carriers=members)
    storage = in_memory_history()
    draft = asyncio.run(
        storage.create(title="split", author_id="owner", ref_score_id=None, document=score.document)
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=storage)
    auth = Mock()
    from piano_app.application.errors import InvalidAccessTokenError

    def authenticate(*, token: str | None) -> str:
        if token != "owner":
            raise InvalidAccessTokenError()
        return "owner"

    auth.authenticate_access_token.side_effect = authenticate
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_edit_router(service=service, current_user=CurrentUser(service=auth)))
    held = ClientView(storage=storage, draft_id=draft.draft_id)
    with TestClient(app) as client:
        path = f"/drafts/{draft.draft_id}/edit/presentation"
        headers = {"Authorization": "Bearer owner"}
        body = {
            "changes": [
                {
                    "kind": "endpoints",
                    "target": {"entity_id": beam.id, "reference": "body"},
                    "offsets": {"left": 0.75, "right": 1.5},
                }
            ]
        }
        assert client.put(path, json=body).status_code == 401
        response = client.put(path, headers=headers, json=body)
        assert response.status_code == 200, response.text

        def offsets(document: dict[str, object]) -> object:
            return next(
                (
                    {"left": r["left"], "right": r["right"]}
                    for r in document["presentation"]["endpoints"]
                    if r["entity_id"] == beam.id
                ),
                None,
            )

        assert offsets(held.apply(sync=response.json()["sync"])) == body["changes"][0]["offsets"]
        undone = asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
        assert offsets(undone.view.jsonify()) is None
        redone = asyncio.run(service.redo(draft_id=draft.draft_id, actor_id="owner"))
        assert offsets(redone.view.jsonify()) == body["changes"][0]["offsets"]
        # undo and redo went past the client: it takes the draft whole again
        held = ClientView(storage=storage, draft_id=draft.draft_id)
        reset = client.put(
            path,
            headers=headers,
            json={
                "changes": [
                    {
                        "kind": "endpoints",
                        "target": {"entity_id": beam.id, "reference": "body"},
                        "offsets": None,
                    }
                ]
            },
        )
        assert reset.status_code == 200
        assert offsets(held.apply(sync=reset.json()["sync"])) is None
        refused = client.put(
            path,
            headers=headers,
            json={
                "changes": [
                    {
                        "kind": "endpoints",
                        "target": {"entity_id": members[0].id, "reference": "body"},
                        "offsets": None,
                    }
                ]
            },
        )
        assert refused.status_code == 422
