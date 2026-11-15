import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import CreateBeamRequest
from piano_app.domain.score.document.services.mutation.compiler import CreateBeamIntent


@pytest.mark.unit
def test_a_beam_request_beams_its_carriers_in_the_order_given() -> None:
    request: CreateBeamRequest = CreateBeamRequest.model_validate({"carrier_ids": ["a", "b"]})

    assert request.to_intent() == CreateBeamIntent(carrier_ids=("a", "b"))


@pytest.mark.unit
def test_a_beam_request_without_carriers_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        CreateBeamRequest.model_validate({})


@pytest.mark.unit
def test_split_request_addresses_a_beam_and_the_carrier_before_which_to_break() -> None:
    from piano_app.adapters.inbound.http.score.edit.requests import SplitBeamRequest
    from piano_app.domain.score.document.services.mutation.compiler import SplitBeamIntent

    request = SplitBeamRequest.model_validate({"beam_id": "beam", "before_carrier_id": "third"})
    assert request.to_intent() == SplitBeamIntent(beam_id="beam", before_carrier_id="third")


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"beam_id": "beam"},
        {"before_carrier_id": "third"},
        {"beam_id": None, "before_carrier_id": "third"},
    ],
)
def test_split_request_requires_both_ids(body: dict[str, object]) -> None:
    from piano_app.adapters.inbound.http.score.edit.requests import SplitBeamRequest

    with pytest.raises(ValidationError):
        SplitBeamRequest.model_validate(body)


@pytest.mark.unit
def test_http_split_uses_real_engine_history_and_preserves_carriers() -> None:
    import asyncio
    from fractions import Fraction
    from unittest.mock import Mock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.unit.domain.scene import build_score, note, rest

    from piano_app.adapters.inbound.http.current_user import CurrentUser
    from piano_app.adapters.inbound.http.errors import register_exception_handlers
    from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
    from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
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
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="split", author_id="owner", ref_score_id=None, document=score.document)
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=storage)
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_edit_router(service=service, current_user=CurrentUser(service=auth)))
    with TestClient(app) as client:
        path = f"/drafts/{draft.draft_id}/edit/beams/split"
        headers = {"Authorization": "Bearer owner"}
        refused = client.post(
            path, headers=headers, json={"beam_id": beam.id, "before_carrier_id": members[0].id}
        )
        assert refused.status_code == 422
        response = client.post(
            path, headers=headers, json={"beam_id": beam.id, "before_carrier_id": members[2].id}
        )
        assert response.status_code == 200, response.text
        view = response.json()["document"]
        beams = [relation for relation in view["relations"] if relation["kind"] == "beam"]
        assert [relation["carrier_ids"] for relation in beams] == [
            [m.id for m in members[:2]],
            [m.id for m in members[2:]],
        ]
        assert all(m.id in {carrier["id"] for carrier in view["carriers"]} for m in members)
        asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
        current = asyncio.run(storage.get(draft_id=draft.draft_id))
        assert current is not None
        from piano_app.domain.score.document.services.helpers import find_beams, iter_leaves

        carriers = [
            leaf.carrier
            for leaf in iter_leaves(current.document.voices[0])
            if leaf.carrier is not None
        ]
        assert [[m.id for m in found.members] for found in find_beams(carriers=carriers)] == [
            [m.id for m in members]
        ]
        asyncio.run(service.redo(draft_id=draft.draft_id, actor_id="owner"))
        current = asyncio.run(storage.get(draft_id=draft.draft_id))
        assert current is not None
        carriers = [
            leaf.carrier
            for leaf in iter_leaves(current.document.voices[0])
            if leaf.carrier is not None
        ]
        assert len(find_beams(carriers=carriers)) == 2
