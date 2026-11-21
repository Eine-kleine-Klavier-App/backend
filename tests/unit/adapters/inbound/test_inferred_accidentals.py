import asyncio
from dataclasses import dataclass
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fixtures.drafts import in_memory_history
from tests.fixtures.sync import ClientView
from tests.unit.domain.pitch.test_accidental_inference import key

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine


@dataclass
class Scene:
    app: FastAPI
    storage: DraftHistoryService
    draft_id: str
    document: ScoreDocument
    held: ClientView


@pytest.fixture
def scene() -> Scene:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=3, measure_count=3)
    key(document, Fraction(0), (Accidental.SHARP,) + (Accidental.NATURAL,) * 6)
    storage = in_memory_history()
    draft = asyncio.run(
        storage.create(title="inference", author_id="owner", ref_score_id=None, document=document)
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
    return Scene(app, storage, draft.draft_id, document, held)


def body(scene: Scene, at: Fraction, **changes: object) -> dict[str, object]:
    return {
        "voice_id": scene.document.voices[0].id,
        "staff_id": scene.document.staffs[0].id,
        "measure_id": scene.document.measures[int(at)].id,
        "position": {
            "numerator": (at - int(at)).numerator,
            "denominator": (at - int(at)).denominator,
        },
        "written_value": {"value": 4, "dots": 0},
        "staff_step": -2,
        **changes,
    }


def post(
    client: TestClient, scene: Scene, payload: dict[str, object], suffix: str = "notes"
) -> dict:
    response = client.post(
        f"/drafts/{scene.draft_id}/edit/{suffix}",
        headers={"Authorization": "Bearer owner"},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return scene.held.apply(sync=response.json()["sync"])


def notes_at(view: dict, at: Fraction, *, voice: int = 0) -> list[dict]:
    containers = {c["id"]: c for c in view["rhythmic_containers"]}
    pending = list(view["voices"][voice]["rhythmic_container_ids"])
    ids: set[str] = set()
    while pending:
        container = containers[pending.pop()]
        ids.add(container["id"])
        pending.extend(container.get("child_ids", []))
    leaf = next(
        c
        for c in containers.values()
        if c["kind"] == "leaf"
        and c["id"] in ids
        and c["measure_id"] == view["measures"][int(at)]["id"]
        and Fraction(c["position"]["numerator"], c["position"]["denominator"]) == at - int(at)
    )
    carrier = next(c for c in view["carriers"] if c["id"] == leaf["carrier_id"])
    return [item for item in view["items"] if item["id"] in carrier["note_ids"]]


@pytest.mark.parametrize("supplied", [{}, {"accidental": None}])
def test_missing_and_null_resolve_key_and_store_concrete_pitch(
    scene: Scene, supplied: dict
) -> None:
    with TestClient(scene.app) as client:
        view = post(client, scene, body(scene, Fraction(0), **supplied))
    (selected,) = notes_at(view, Fraction(0))
    assert (selected["accidental"], selected["midi_note"]) == ("sharp", 61)
    assert all(item["accidental"] is not None for item in view["items"] if item["kind"] == "note")


def test_other_voice_local_flat_overrides_key_and_reset_is_per_measure(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        post(
            client,
            scene,
            body(scene, Fraction(0), accidental="flat", voice_id=scene.document.voices[1].id),
        )
        view = post(client, scene, body(scene, Fraction(1, 4), accidental=None))
        (selected,) = notes_at(view, Fraction(1, 4))
        assert (selected["accidental"], selected["midi_note"]) == ("flat", 59)
        (previous,) = notes_at(view, Fraction(0), voice=1)
        assert previous["accidental"] == "flat"
        view = post(client, scene, body(scene, Fraction(1), accidental=None))
        (selected,) = notes_at(view, Fraction(1))
        assert (selected["accidental"], selected["midi_note"]) == ("sharp", 61)


def test_explicit_natural_is_not_inference_and_later_none_inherits_it(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        post(client, scene, body(scene, Fraction(0), accidental="sharp"))
        view = post(client, scene, body(scene, Fraction(1, 4), accidental="natural"))
        (selected,) = notes_at(view, Fraction(1, 4))
        assert (selected["accidental"], selected["midi_note"]) == ("natural", 60)
        view = post(client, scene, body(scene, Fraction(1, 2)))
        (selected,) = notes_at(view, Fraction(1, 2))
        assert selected["accidental"] == "natural"


@pytest.mark.parametrize("supplied", [{}, {"accidental": None}])
def test_first_tuplet_note_inherits_local_sign(scene: Scene, supplied: dict) -> None:
    with TestClient(scene.app) as client:
        post(
            client,
            scene,
            body(scene, Fraction(0), accidental="flat", voice_id=scene.document.voices[1].id),
        )
        payload = body(scene, Fraction(1, 4))
        del payload["staff_step"]
        payload.update(
            {
                "written_value": {"value": 8},
                "written_size": {"value": {"value": 8}, "count": 3},
                "occupied_size": {"value": {"value": 8}, "count": 2},
                "note": {"staff_step": -2, **supplied},
            }
        )
        view = post(client, scene, payload, "tuplets")
    (selected,) = notes_at(view, Fraction(1, 4))
    assert (selected["accidental"], selected["midi_note"]) == ("flat", 59)


def test_different_previous_signs_allow_copying_and_explicit_sign_bypasses_inference(
    scene: Scene,
) -> None:
    with TestClient(scene.app) as client:
        post(client, scene, body(scene, Fraction(0), accidental="flat"))
        post(
            client,
            scene,
            body(scene, Fraction(0), accidental="sharp", voice_id=scene.document.voices[1].id),
        )
        before = asyncio.run(scene.storage.get(draft_id=scene.draft_id))
        assert before is not None
        view = post(client, scene, body(scene, Fraction(1, 4), accidental=None))
        (selected,) = notes_at(view, Fraction(1, 4))
        assert (selected["accidental"], selected["midi_note"]) == ("flat", 59)
        after = asyncio.run(scene.storage.get(draft_id=scene.draft_id))
        assert after is not None and after.version > before.version
        view = post(client, scene, body(scene, Fraction(1, 2), accidental="natural"))
        (selected,) = notes_at(view, Fraction(1, 2))
        assert (selected["accidental"], selected["midi_note"]) == ("natural", 60)


def test_inferred_sign_survives_barline_slicing_and_a_different_key_in_next_measure(
    scene: Scene,
) -> None:
    # Configure the next key on the original snapshot, then create a fresh history entry for it.
    key(scene.document, Fraction(1), (Accidental.FLAT,) * 7)
    draft = asyncio.run(
        scene.storage.create(
            title="cross-bar", author_id="owner", ref_score_id=None, document=scene.document
        )
    )
    scene.draft_id = draft.draft_id
    with TestClient(scene.app) as client:
        view = post(
            client, scene, body(scene, Fraction(3, 4), accidental=None, written_value={"value": 2})
        )
    (first,) = notes_at(view, Fraction(3, 4))
    (second,) = notes_at(view, Fraction(1))
    assert first["accidental"] == second["accidental"] == "sharp"
    assert first["midi_note"] == second["midi_note"] == 61
    assert any(r["kind"] == "tie" for r in view["relations"])


def test_first_tuplet_note_copies_previous_sign_without_comparing_other_voices(
    scene: Scene,
) -> None:
    with TestClient(scene.app) as client:
        post(client, scene, body(scene, Fraction(0), accidental="flat"))
        post(
            client,
            scene,
            body(scene, Fraction(0), accidental="sharp", voice_id=scene.document.voices[1].id),
        )
        before = asyncio.run(scene.storage.get(draft_id=scene.draft_id))
        payload = body(scene, Fraction(1, 4))
        del payload["staff_step"]
        payload.update(
            {
                "written_value": {"value": 8},
                "written_size": {"value": {"value": 8}, "count": 3},
                "occupied_size": {"value": {"value": 8}, "count": 2},
                "note": {"staff_step": -2, "accidental": None},
            }
        )
        view = post(client, scene, payload, "tuplets")
        (selected,) = notes_at(view, Fraction(1, 4))
        assert (selected["accidental"], selected["midi_note"]) == ("flat", 59)
        assert any(
            container["kind"] == "group"
            and container["written_size"] != container["occupied_size"]
            and container["child_ids"]
            for container in view["rhythmic_containers"]
        )
        after = asyncio.run(scene.storage.get(draft_id=scene.draft_id))
        assert before is not None and after is not None and after.version > before.version


def test_invalid_sign_still_rejected_at_http_boundary(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/edit/notes",
            headers={"Authorization": "Bearer owner"},
            json=body(scene, Fraction(0), accidental="none"),
        )
    assert response.status_code == 422
