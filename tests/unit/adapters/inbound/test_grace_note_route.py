import asyncio
from dataclasses import dataclass
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.domain.pitch.test_accidental_inference import key

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

# The grace note routes, from the request to the view the client gets back. The key signature
# puts a sharp on staff step -2, the step every note here stands on.
_STEP: int = -2


@dataclass
class Scene:
    app: FastAPI
    draft_id: str
    document: ScoreDocument


@pytest.fixture
def scene() -> Scene:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    key(document, Fraction(0), (Accidental.SHARP,) + (Accidental.NATURAL,) * 6)
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="graces", author_id="owner", ref_score_id=None, document=document)
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
    return Scene(app, draft.draft_id, document)


def post(
    client: TestClient, scene: Scene, suffix: str, payload: dict[str, object], *, status: int = 200
) -> dict:
    response = client.post(
        f"/drafts/{scene.draft_id}/edit/{suffix}",
        headers={"Authorization": "Bearer owner"},
        json=payload,
    )
    assert response.status_code == status, response.text
    return response.json()


def insert_host(client: TestClient, scene: Scene, accidental: str) -> str:
    """A quarter note on the first beat; returns the id of its carrier."""
    view = post(
        client,
        scene,
        "notes",
        {
            "voice_id": scene.document.voices[0].id,
            "staff_id": scene.document.staffs[0].id,
            "measure_id": scene.document.measures[0].id,
            "position": {"numerator": 0, "denominator": 1},
            "written_value": {"value": 4, "dots": 0},
            "staff_step": _STEP,
            "accidental": accidental,
        },
    )["document"]
    return next(row["id"] for row in view["carriers"] if row["kind"] == "chord")


def grace(
    scene: Scene, host_carrier_id: str, placement: str, *, value: int = 16, **changes: object
) -> dict[str, object]:
    return {
        "host_carrier_id": host_carrier_id,
        "placement": placement,
        "grace_type": "appoggiatura",
        "written_value": {"value": value, "dots": 0},
        "staff_id": scene.document.staffs[0].id,
        "staff_step": _STEP,
        **changes,
    }


def leaf_of(view: dict, carrier_id: str) -> dict:
    return next(row for row in view["rhythmic_containers"] if row.get("carrier_id") == carrier_id)


def grace_notes(view: dict, group: dict) -> list[dict]:
    carriers = {row["id"]: row for row in view["carriers"]}
    note_ids = {
        note_id for item in group["items"] for note_id in carriers[item["carrier_id"]]["note_ids"]
    }
    return [row for row in view["items"] if row["id"] in note_ids]


def test_a_grace_note_is_added_and_the_view_shows_it_and_the_time_it_takes(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(
            client, scene, "grace-notes", grace(scene, host, "before", value=8, accidental="sharp")
        )["document"]

    leaf = leaf_of(view, host)
    assert leaf["grace_after"] is None
    assert leaf["grace_taken"] == {"numerator": 1, "denominator": 8}
    (written,) = grace_notes(view, leaf["grace_before"])
    (host_note,) = (
        row for row in view["items"] if row["kind"] == "note" and row["id"] != written["id"]
    )
    # the same step as the host, a sharp against its natural
    assert written["accidental"] == "sharp"
    assert written["midi_note"] == host_note["midi_note"] + 1


def test_a_sign_left_out_is_read_from_the_cell_of_the_grace_note(scene: Scene) -> None:
    """Host natural, key sharp: a grace note before does not see the host, one after does."""
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        post(client, scene, "grace-notes", grace(scene, host, "before"))
        view = post(client, scene, "grace-notes", grace(scene, host, "after"))["document"]

    leaf = leaf_of(view, host)
    (before,) = grace_notes(view, leaf["grace_before"])
    (after,) = grace_notes(view, leaf["grace_after"])
    assert before["accidental"] == "sharp"
    assert after["accidental"] == "natural"


def test_grace_notes_that_would_take_all_the_time_of_their_note_are_refused(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        post(client, scene, "grace-notes", grace(scene, host, "before", value=8))
        post(client, scene, "grace-notes", grace(scene, host, "before", value=8), status=422)

        # the refused one left nothing behind
        view = post(client, scene, "grace-notes", grace(scene, host, "after", value=32))["document"]

    leaf = leaf_of(view, host)
    assert len(leaf["grace_before"]["items"]) == 1
    assert len(leaf["grace_after"]["items"]) == 1


def test_removing_the_last_grace_note_takes_its_group_away(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(client, scene, "grace-notes", grace(scene, host, "before"))["document"]
        (written,) = grace_notes(view, leaf_of(view, host)["grace_before"])

        view = post(client, scene, "grace-note-removals", {"note_id": written["id"]})["document"]

    leaf = leaf_of(view, host)
    assert leaf["grace_before"] is None
    assert leaf["grace_taken"] == {"numerator": 0, "denominator": 1}


def test_a_grace_note_of_an_unknown_note_is_refused(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        insert_host(client, scene, "natural")
        post(client, scene, "grace-notes", grace(scene, "no-such-carrier", "before"), status=422)


def test_a_group_changes_its_kind_and_the_view_shows_the_time_it_now_takes(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(
            client,
            scene,
            "grace-notes",
            grace(scene, host, "before", value=8, grace_type="acciaccatura"),
        )["document"]
        (written,) = grace_notes(view, leaf_of(view, host)["grace_before"])
        assert leaf_of(view, host)["grace_taken"] == {"numerator": 1, "denominator": 32}

        view = post(
            client,
            scene,
            "grace-type-changes",
            {"note_id": written["id"], "grace_type": "appoggiatura"},
        )["document"]

    leaf = leaf_of(view, host)
    assert leaf["grace_before"]["grace_type"] == "appoggiatura"
    assert leaf["grace_taken"] == {"numerator": 1, "denominator": 8}


def test_a_kind_that_would_take_all_the_time_of_the_note_is_refused(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        for _ in range(3):
            view = post(
                client,
                scene,
                "grace-notes",
                grace(scene, host, "before", value=8, grace_type="acciaccatura"),
            )["document"]
        (first, *_rest) = grace_notes(view, leaf_of(view, host)["grace_before"])

        post(
            client,
            scene,
            "grace-type-changes",
            {"note_id": first["id"], "grace_type": "appoggiatura"},
            status=422,
        )


def grace_carriers(view: dict, group: dict) -> list[dict]:
    """The carriers of a group in its order, each with the staff steps of its notes."""
    carriers = {row["id"]: row for row in view["carriers"]}
    notes = {row["id"]: row for row in view["items"]}
    return [
        {
            "id": item["carrier_id"],
            "steps": [
                notes[note_id]["staff_step"] for note_id in carriers[item["carrier_id"]]["note_ids"]
            ],
        }
        for item in group["items"]
    ]


def test_a_grace_carrier_is_put_after_the_one_named_and_first_when_none_is(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(
            client, scene, "grace-notes", grace(scene, host, "before", value=32, staff_step=0)
        )["document"]
        (first,) = grace_carriers(view, leaf_of(view, host)["grace_before"])
        post(
            client,
            scene,
            "grace-notes",
            grace(scene, host, "before", value=32, staff_step=1, after_carrier_id=first["id"]),
        )
        view = post(
            client,
            scene,
            "grace-notes",
            grace(scene, host, "before", value=32, staff_step=2, after_carrier_id=first["id"]),
        )["document"]
        view = post(
            client, scene, "grace-notes", grace(scene, host, "before", value=32, staff_step=3)
        )["document"]

    order = [row["steps"] for row in grace_carriers(view, leaf_of(view, host)["grace_before"])]
    assert order == [[3], [0], [2], [1]]


def test_a_carrier_that_is_not_in_the_group_cannot_be_named_as_the_place(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        post(
            client,
            scene,
            "grace-notes",
            grace(scene, host, "before", after_carrier_id=host),
            status=422,
        )


def test_a_note_joins_a_grace_carrier(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(
            client, scene, "grace-notes", grace(scene, host, "before", value=32, staff_step=0)
        )["document"]
        (carrier,) = grace_carriers(view, leaf_of(view, host)["grace_before"])
        view = post(
            client,
            scene,
            "grace-carrier-notes",
            {
                "carrier_id": carrier["id"],
                "staff_id": scene.document.staffs[0].id,
                "staff_step": 2,
            },
        )["document"]

    leaf = leaf_of(view, host)
    assert [row["steps"] for row in grace_carriers(view, leaf["grace_before"])] == [[0, 2]]
    assert leaf["grace_taken"] == {"numerator": 1, "denominator": 32}


def test_a_note_cannot_join_a_carrier_that_is_not_a_grace_carrier(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        post(
            client,
            scene,
            "grace-carrier-notes",
            {"carrier_id": host, "staff_id": scene.document.staffs[0].id, "staff_step": 2},
            status=422,
        )


def test_a_grace_carrier_is_written_as_another_value(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        host = insert_host(client, scene, "natural")
        view = post(client, scene, "grace-notes", grace(scene, host, "before", value=16))[
            "document"
        ]
        (carrier,) = grace_carriers(view, leaf_of(view, host)["grace_before"])
        view = post(
            client,
            scene,
            "grace-value-changes",
            {"carrier_id": carrier["id"], "written_value": {"value": 8, "dots": 0}},
        )["document"]

    leaf = leaf_of(view, host)
    assert leaf["grace_before"]["items"][0]["rhythmic_value"] == {"value": 8, "dots": 0}
    assert leaf["grace_taken"] == {"numerator": 1, "denominator": 8}
