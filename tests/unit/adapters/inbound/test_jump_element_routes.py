import asyncio
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.fixtures.drafts import in_memory_history
from tests.fixtures.sync import ClientView

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.requests import (
    CreateRefrainRequest,
    CreateVoltaRequest,
    MoveRefrainEndRequest,
)
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateRefrainIntent,
    CreateVoltaIntent,
    MoveRefrainEndIntent,
    VoltaFragmentIntent,
)

_ZERO: dict[str, int] = {"numerator": 0, "denominator": 1}
_HEADERS: dict[str, str] = {"Authorization": "Bearer owner"}


def _client() -> tuple[TestClient, ClientView, str, list[str]]:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=1, measure_count=7
    )
    storage = in_memory_history()
    draft = asyncio.run(
        storage.create(title="jumps", author_id="owner", ref_score_id=None, document=document)
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
    held = ClientView(storage=storage, draft_id=draft.draft_id)
    return TestClient(app), held, draft.draft_id, [measure.id for measure in document.measures]


def _rows(*, view: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [row for row in view["contexts"] if row["kind"] == kind]


def _post(client: TestClient, draft_id: str, path: str, json: dict[str, Any]) -> Any:
    return client.post(f"/drafts/{draft_id}/edit/{path}", headers=_HEADERS, json=json)


def _put(client: TestClient, draft_id: str, path: str, json: dict[str, Any]) -> Any:
    return client.put(f"/drafts/{draft_id}/edit/{path}", headers=_HEADERS, json=json)


def test_the_refrain_routes_make_change_and_end_a_refrain() -> None:
    client, held, draft_id, measures = _client()

    created = _post(
        client,
        draft_id,
        "refrains",
        {
            "start_measure_id": measures[0],
            "start_position": _ZERO,
            "end_measure_id": measures[2],
            "end_position": _ZERO,
            "times": 3,
        },
    )

    assert created.status_code == 200, created.text
    (refrain,) = _rows(view=held.apply(sync=created.json()["sync"]), kind="refrain")
    assert refrain["times"] == 3
    assert refrain["end_measure_id"] == measures[2]

    more = _put(client, draft_id, "refrain-times", {"refrain_id": refrain["id"], "times": 5})
    assert _rows(view=held.apply(sync=more.json()["sync"]), kind="refrain")[0]["times"] == 5

    moved = _put(
        client,
        draft_id,
        "refrain-ends",
        {"refrain_id": refrain["id"], "measure_id": measures[4], "position": _ZERO},
    )
    assert (
        _rows(view=held.apply(sync=moved.json()["sync"]), kind="refrain")[0]["end_measure_id"]
        == measures[4]
    )

    opened = _put(client, draft_id, "refrain-ends", {"refrain_id": refrain["id"]})
    assert (
        _rows(view=held.apply(sync=opened.json()["sync"]), kind="refrain")[0]["end_measure_id"]
        is None
    )

    refused = _put(client, draft_id, "refrain-times", {"refrain_id": refrain["id"], "times": 1})
    assert refused.status_code == 422


def test_the_volta_routes_make_a_volta_and_reshape_it() -> None:
    client, held, draft_id, measures = _client()

    created = _post(
        client,
        draft_id,
        "voltas",
        {
            "start_measure_id": measures[0],
            "start_position": _ZERO,
            "body_end_measure_id": measures[2],
            "body_end_position": _ZERO,
            "fragments": [
                {"end_measure_id": measures[3], "end_position": _ZERO, "passes": [1, 3]},
                {"end_measure_id": measures[4], "end_position": _ZERO, "passes": [2]},
            ],
        },
    )

    assert created.status_code == 200, created.text
    (volta,) = _rows(view=held.apply(sync=created.json()["sync"]), kind="volta")
    assert volta["pass_count"] == 4
    assert [fragment["passes"] for fragment in volta["fragments"]] == [[1, 3], [2]]

    absorbed = _put(
        client,
        draft_id,
        "volta-boundaries",
        {
            "volta_id": volta["id"],
            "boundary": 1,
            "measure_id": measures[4],
            "position": _ZERO,
        },
    )
    (after,) = _rows(view=held.apply(sync=absorbed.json()["sync"]), kind="volta")
    assert after["pass_count"] == 3
    assert [fragment["passes"] for fragment in after["fragments"]] == [[1, 2]]

    longer = _post(
        client,
        draft_id,
        "volta-fragments",
        {"volta_id": volta["id"], "measure_id": measures[5], "position": _ZERO},
    )
    (grown,) = _rows(view=held.apply(sync=longer.json()["sync"]), kind="volta")
    assert [fragment["passes"] for fragment in grown["fragments"]] == [[1, 2], [3]]
    assert grown["pass_count"] == 4

    named = _put(
        client,
        draft_id,
        "volta-fragment-passes",
        {"volta_id": volta["id"], "fragment": 1, "passes": [2, 3]},
    )
    (renamed,) = _rows(view=held.apply(sync=named.json()["sync"]), kind="volta")
    assert [fragment["passes"] for fragment in renamed["fragments"]] == [[1], [2, 3]]

    refused = _put(
        client,
        draft_id,
        "volta-fragment-passes",
        {"volta_id": volta["id"], "fragment": 0, "passes": [1]},
    )
    assert refused.status_code == 422
    assert "the others leave" in refused.text

    longer_run = _put(client, draft_id, "volta-times", {"volta_id": volta["id"], "times": 5})
    (played_five,) = _rows(view=held.apply(sync=longer_run.json()["sync"]), kind="volta")
    assert played_five["pass_count"] == 5
    assert [fragment["passes"] for fragment in played_five["fragments"]] == [[1, 4], [2, 3]]

    too_few = _put(client, draft_id, "volta-times", {"volta_id": volta["id"], "times": 3})
    assert too_few.status_code == 422
    assert "no longer have" in too_few.text


def test_the_refrain_ending_route_turns_a_repeat_into_a_volta() -> None:
    client, held, draft_id, measures = _client()
    created = _post(
        client,
        draft_id,
        "refrains",
        {
            "start_measure_id": measures[0],
            "start_position": _ZERO,
            "end_measure_id": measures[2],
            "end_position": _ZERO,
            "times": 2,
        },
    )
    (refrain,) = _rows(view=held.apply(sync=created.json()["sync"]), kind="refrain")

    turned = _post(
        client,
        draft_id,
        "refrain-endings",
        {"refrain_id": refrain["id"], "end_measure_id": measures[3], "end_position": _ZERO},
    )

    assert turned.status_code == 200, turned.text
    view = held.apply(sync=turned.json()["sync"])
    assert _rows(view=view, kind="refrain") == []
    (volta,) = _rows(view=view, kind="volta")
    assert volta["pass_count"] == 2
    assert [fragment["passes"] for fragment in volta["fragments"]] == [[1]]


def test_a_volta_is_cut_and_its_body_moved_by_their_routes() -> None:
    client, held, draft_id, measures = _client()
    created = _post(
        client,
        draft_id,
        "voltas",
        {
            "start_measure_id": measures[1],
            "start_position": _ZERO,
            "body_end_measure_id": measures[3],
            "body_end_position": _ZERO,
            "fragments": [{"end_measure_id": measures[6], "end_position": _ZERO, "passes": [1]}],
        },
    )
    (volta,) = _rows(view=held.apply(sync=created.json()["sync"]), kind="volta")

    cut = _post(
        client,
        draft_id,
        "volta-fragment-splits",
        {"volta_id": volta["id"], "measure_id": measures[5], "position": _ZERO},
    )
    (split,) = _rows(view=held.apply(sync=cut.json()["sync"]), kind="volta")
    assert [fragment["passes"] for fragment in split["fragments"]] == [[1], [2]]

    moved = _put(
        client,
        draft_id,
        "volta-starts",
        {"volta_id": volta["id"], "measure_id": measures[2], "position": _ZERO},
    )
    (after,) = _rows(view=held.apply(sync=moved.json()["sync"]), kind="volta")
    assert after["measure_id"] == measures[2]


@pytest.mark.unit
def test_the_requests_turn_into_their_intents_and_refuse_a_missing_part() -> None:
    position = MeasurePosition.of(numerator=0, denominator=1)

    refrain = CreateRefrainRequest.model_validate(
        {"start_measure_id": "m", "start_position": _ZERO, "times": 2}
    )
    assert refrain.to_intent() == CreateRefrainIntent(
        start_measure_id="m",
        start_position=position,
        end_measure_id=None,
        end_position=None,
        times=2,
    )

    assert MoveRefrainEndRequest.model_validate({"refrain_id": "r"}).to_intent() == (
        MoveRefrainEndIntent(refrain_id="r", measure_id=None, position=None)
    )

    volta = CreateVoltaRequest.model_validate(
        {
            "start_measure_id": "a",
            "start_position": _ZERO,
            "body_end_measure_id": "b",
            "body_end_position": _ZERO,
            "fragments": [{"passes": [1]}],
        }
    )
    assert volta.to_intent() == CreateVoltaIntent(
        start_measure_id="a",
        start_position=position,
        body_end_measure_id="b",
        body_end_position=position,
        fragments=(VoltaFragmentIntent(end_measure_id=None, end_position=None, passes=(1,)),),
    )

    with pytest.raises(ValidationError):
        CreateRefrainRequest.model_validate(
            {"start_measure_id": "m", "start_position": _ZERO, "times": 1}
        )

    with pytest.raises(ValidationError):
        CreateVoltaRequest.model_validate(
            {
                "start_measure_id": "a",
                "start_position": _ZERO,
                "body_end_measure_id": "b",
                "body_end_position": _ZERO,
                "fragments": [],
            }
        )
