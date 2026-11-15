import asyncio
import json
from collections.abc import Callable, Generator
from dataclasses import dataclass
from fractions import Fraction
from unittest.mock import Mock

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.edit.router import build_edit_router
from piano_app.adapters.inbound.http.score.playback import build_playback_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import InvalidAccessTokenError
from piano_app.application.ports.playback import AudioChunk
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.application.use_cases.score.playback import PlaybackService
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import DynamicChange, TempoChange
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.playback import PlaybackProjection, build_projection


class RecordingRenderer:
    def __init__(self) -> None:
        self.projections: list[PlaybackProjection] = []
        self.closed = False
        self.cancelled = False
        self.fail = False

    def stream(
        self, *, projection: PlaybackProjection, cancelled: Callable[[], bool] | None = None
    ) -> Generator[AudioChunk]:
        self.projections.append(projection)
        try:
            if self.fail:
                raise RuntimeError("native failure, not for the client")
            if projection.extent_ms == 0:
                return
            for offset in (0, 10):
                yield AudioChunk(pcm=b"\x01\x00" * 20, start_frame=offset, sample_rate=8000)
        finally:
            self.closed = True
            self.cancelled = cancelled is not None and cancelled()


@dataclass
class Scene:
    app: FastAPI
    storage: InMemoryDraftHistory
    renderer: RecordingRenderer
    draft_id: str
    document: ScoreDocument
    carrier_id: str


@pytest.fixture
def scene() -> Scene:
    document = score()
    start = anchor(document, Fraction(0))
    for context in tuple(start.starting_contexts):
        if isinstance(context, TempoChange):
            context.detach()

    TempoChange.create(start=start, beat=DottedRhythmicValue(value=RhythmicValue.QUARTER), bpm=120)
    selected = note(document, Fraction(0), value=RhythmicValue.HALF)
    note(document, Fraction(1, 2))
    DynamicChange.create(
        start=anchor(document, Fraction(1, 4)),
        voices=[document.voices[0]],
        dynamic=DynamicMarking.FORTE,
    )
    storage = InMemoryDraftHistory()
    draft = asyncio.run(
        storage.create(title="test", author_id="owner", ref_score_id=None, document=document)
    )
    renderer = RecordingRenderer()
    auth = Mock()

    def authenticate(*, token: str | None) -> str:
        if token not in ("owner", "other"):
            raise InvalidAccessTokenError()
        return token

    auth.authenticate_access_token.side_effect = authenticate
    current = CurrentUser(service=auth)
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_playback_router(
            service=PlaybackService(storage=storage, renderer=renderer), current_user=current
        )
    )
    app.include_router(
        build_edit_router(
            service=ScoreEditService(
                engine=build_engine(), compiler=build_compiler(), history=storage
            ),
            current_user=current,
        )
    )
    return Scene(app, storage, renderer, draft.draft_id, document, selected.note_carrier.id)


def test_start_coordinate_reaches_projection_and_stream_headers(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json={"start": {"numerator": 1, "denominator": 4}},
        )
    assert response.status_code == 200
    assert response.content == b"\x01\x00" * 40
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-audio-sample-rate"] == "8000"
    assert response.headers["x-audio-format"] == "s16le"
    assert response.headers["x-audio-channels"] == "2"
    assert response.headers["x-draft-version"] == "0"
    assert response.headers["cache-control"] == "no-store"
    projection = scene.renderer.projections[0]
    assert projection.extent_ms == pytest.approx(5500)
    # the half note sounds through the start, so it is struck again with what is left of it
    assert [(n.start_ms, n.end_ms, n.velocity) for n in projection.notes] == [
        (pytest.approx(0), pytest.approx(500), 31),
        (pytest.approx(500), pytest.approx(1000), 111),
    ]
    assert scene.renderer.closed


def test_preview_only_selected_carrier(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback/preview",
            headers={"Authorization": "Bearer owner"},
            json={"carrier_id": scene.carrier_id},
        )
    assert response.status_code == 200
    projection = scene.renderer.projections[0]
    assert len(projection.notes) == 1
    assert projection.notes[0].end_ms - projection.notes[0].start_ms == 650
    assert projection.notes[0].velocity == 31


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"start": {"numerator": -1, "denominator": 4}},
        {"start": {"numerator": 1, "denominator": 0}},
        {"start": {"numerator": 1.5, "denominator": 4}},
        {"start": {"numerator": True, "denominator": 4}},
    ],
)
def test_invalid_coordinate_is_422_before_synthesis(scene: Scene, body: object) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json=body,
        )
    assert response.status_code == 422
    assert scene.renderer.projections == []


def test_authentication_ownership_missing_and_outside(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        body = {"start": {"numerator": 0, "denominator": 1}}
        assert client.post(f"/drafts/{scene.draft_id}/playback", json=body).status_code == 401
        assert (
            client.post(
                f"/drafts/{scene.draft_id}/playback",
                headers={"Authorization": "Bearer other"},
                json=body,
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/drafts/missing/playback", headers={"Authorization": "Bearer owner"}, json=body
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/drafts/{scene.draft_id}/playback",
                headers={"Authorization": "Bearer owner"},
                json={"start": {"numerator": 4, "denominator": 1}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/drafts/{scene.draft_id}/playback/preview",
                headers={"Authorization": "Bearer owner"},
                json={"carrier_id": "missing"},
            ).status_code
            == 404
        )
    assert scene.renderer.projections == []


def test_synth_start_failure_returns_503_before_audio_headers(scene: Scene) -> None:
    scene.renderer.fail = True
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json={"start": {"numerator": 0, "denominator": 1}},
        )
    assert response.status_code == 503
    assert "native failure" not in response.text
    assert scene.renderer.closed


def test_start_at_end_returns_204(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json={"start": {"numerator": 3, "denominator": 1}},
        )
    assert response.status_code == 204 and response.content == b""
    assert scene.renderer.closed


async def test_disconnect_closes_native_stream(scene: Scene) -> None:
    body = json.dumps({"start": {"numerator": 0, "denominator": 1}}).encode()
    started = anyio.Event()
    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            started.set()
            await anyio.sleep_forever()

    with anyio.fail_after(3):
        await scene.app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": f"/drafts/{scene.draft_id}/playback",
                "query_string": b"",
                "root_path": "",
                "headers": [
                    (b"authorization", b"Bearer owner"),
                    (b"content-type", b"application/json"),
                ],
                "server": ("test", 80),
                "client": ("test", 123),
            },
            receive,
            send,
        )
    assert scene.renderer.closed and scene.renderer.cancelled


def test_insert_note_then_preview_carrier_uses_new_version(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/edit/notes",
            headers={"Authorization": "Bearer owner"},
            json={
                "voice_id": scene.document.voices[0].id,
                "staff_id": scene.document.staffs[0].id,
                "measure_id": scene.document.measures[1].id,
                "position": {"numerator": 0, "denominator": 1},
                "written_value": {"value": 4},
                "staff_step": 0,
                "accidental": "natural",
            },
        )
        assert response.status_code == 200, response.text
        view = response.json()["document"]
        placed = next(
            c
            for c in view["rhythmic_containers"]
            if c.get("measure_id") == scene.document.measures[1].id and c.get("kind") == "leaf"
        )
        preview = client.post(
            f"/drafts/{scene.draft_id}/playback/preview",
            headers={"Authorization": "Bearer owner"},
            json={"carrier_id": placed["carrier_id"]},
        )
    assert preview.status_code == 200
    assert preview.headers["x-draft-version"] == "1"
    projection = scene.renderer.projections[0]
    assert len(projection.notes) == 1
    assert projection.notes[0].pitch == 64
    assert projection.notes[0].end_ms - projection.notes[0].start_ms == 650
    assert projection.notes[0].velocity == 111


@pytest.mark.integration
def test_http_with_real_fluidsynth(scene: Scene) -> None:
    import os
    from array import array
    from pathlib import Path

    from piano_app.adapters.outbound.fluidsynth import FluidSynthRenderer

    font = os.environ.get("PIANO_TEST_SOUNDFONT")
    if font is None:
        pytest.skip("Set PIANO_TEST_SOUNDFONT for the native HTTP test.")
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_playback_router(
            service=PlaybackService(
                storage=scene.storage,
                renderer=FluidSynthRenderer(
                    soundfont=Path(font),
                    sample_rate=8000,
                    release_ms=100,
                    library_path=os.environ.get("PIANO_FLUIDSYNTH_LIBRARY"),
                ),
            ),
            current_user=CurrentUser(service=auth),
        )
    )
    with TestClient(app) as client:
        preview = client.post(
            f"/drafts/{scene.draft_id}/playback/preview",
            headers={"Authorization": "Bearer owner"},
            json={"carrier_id": scene.carrier_id},
        )
        assert preview.status_code == 200
        assert len(preview.content) == 6000 * 4  # 750 ms, 8000 frames/second, stereo s16
        assert max(abs(n) for n in array("h", preview.content)) > 20
        playback = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json={"start": {"numerator": 1, "denominator": 4}},
        )
        assert playback.status_code == 200
        assert len(playback.content) == 44800 * 4  # 5500 ms of score + 100 ms release
        assert max(abs(n) for n in array("h", playback.content)) > 20


async def test_asgi_send_failure_also_closes_stream(scene: Scene) -> None:
    body = json.dumps({"carrier_id": scene.carrier_id}).encode()

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client closed")

    with pytest.raises(ClientDisconnect):
        await scene.app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": f"/drafts/{scene.draft_id}/playback/preview",
                "query_string": b"",
                "root_path": "",
                "headers": [
                    (b"authorization", b"Bearer owner"),
                    (b"content-type", b"application/json"),
                ],
                "server": ("test", 80),
                "client": ("test", 123),
            },
            receive,
            send,
        )
    assert scene.renderer.closed and scene.renderer.cancelled


def test_adding_note_to_existing_carrier_previews_the_whole_chord(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        inserted = client.post(
            f"/drafts/{scene.draft_id}/edit/notes",
            headers={"Authorization": "Bearer owner"},
            json={
                "voice_id": scene.document.voices[0].id,
                "staff_id": scene.document.staffs[0].id,
                "measure_id": scene.document.measures[0].id,
                "position": {"numerator": 0, "denominator": 1},
                "written_value": {"value": 2},
                "staff_step": 0,
                "accidental": "natural",
            },
        )
        assert inserted.status_code == 200, inserted.text
        preview = client.post(
            f"/drafts/{scene.draft_id}/playback/preview",
            headers={"Authorization": "Bearer owner"},
            json={"carrier_id": scene.carrier_id},
        )
    assert preview.status_code == 200
    assert preview.headers["x-draft-version"] == "1"
    notes = scene.renderer.projections[0].notes
    assert {n.pitch for n in notes} == {60, 64}
    assert all(n.start_ms == 0 and n.end_ms == 650 for n in notes)


def test_unconfigured_synthesis_is_503_for_an_accessible_draft(scene: Scene) -> None:
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_playback_router(
            service=PlaybackService(storage=scene.storage, renderer=None),
            current_user=CurrentUser(service=auth),
        )
    )
    with TestClient(app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner"},
            json={"start": {"numerator": 0, "denominator": 1}},
        )
        map_response = client.get(
            f"/drafts/{scene.draft_id}/playback/map",
            headers={"Authorization": "Bearer owner"},
        )
    assert response.status_code == 503
    assert map_response.status_code == 200
    assert map_response.json()["notes"]


def test_preview_map_needs_access_but_does_not_start_synthesis(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.get(
            f"/drafts/{scene.draft_id}/playback/preview/map",
            headers={"Authorization": "Bearer owner"},
        )
        foreign = client.get(
            f"/drafts/{scene.draft_id}/playback/preview/map",
            headers={"Authorization": "Bearer other"},
        )
    assert response.status_code == 200
    assert foreign.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    carrier = next(c for c in body["carriers"] if c["carrier_id"] == scene.carrier_id)
    assert carrier["notes"][0]["pitch"] == 60
    assert carrier["notes"][0]["duration_ms"] == 650
    assert carrier["notes"][0]["source_id"]
    assert scene.renderer.projections == []


def test_opt_in_map_and_audio_share_snapshot_and_frame_boundary(scene: Scene) -> None:
    import struct

    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback",
            headers={"Authorization": "Bearer owner", "Accept": "application/vnd.piano.playback"},
            json={"start": {"numerator": 0, "denominator": 1}},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.piano.playback"
    (length,) = struct.unpack("<I", response.content[:4])
    metadata = json.loads(response.content[4 : 4 + length])
    assert metadata["version"] == int(response.headers["x-draft-version"])
    assert metadata["extent_ms"] == float(response.headers["x-playback-extent-ms"])
    assert metadata["notes"][0]["source_id"] == scene.renderer.projections[0].notes[0].source_id
    assert metadata["notes"][0]["pitch"] == scene.renderer.projections[0].notes[0].pitch
    assert metadata["notes"][0]["velocity"] == 31
    assert metadata["anchors"][0]["carrier_id"] == scene.carrier_id
    assert metadata["segments"][0]["moments"][-1]["time_ms"] == metadata["extent_ms"]
    assert response.content[4 + length :] == b"\x01\x00" * 40
    assert scene.renderer.closed


def test_map_without_synthesis_uses_same_projection_and_access_rules(scene: Scene) -> None:
    with TestClient(scene.app) as client:
        response = client.get(
            f"/drafts/{scene.draft_id}/playback/map",
            headers={"Authorization": "Bearer owner"},
        )
        unauthorized = client.get(f"/drafts/{scene.draft_id}/playback/map")
        foreign = client.get(
            f"/drafts/{scene.draft_id}/playback/map",
            headers={"Authorization": "Bearer other"},
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    first = response.json()["notes"][0]
    assert first["key_release_ms"] == first["end_ms"]
    assert response.json()["pedals"] == []
    assert first["source_id"] == build_projection(document=scene.document).notes[0].source_id
    assert first["pitch"] == 60
    body = response.json()
    assert body["anchors"][0]["carrier_id"] == scene.carrier_id
    segment = body["segments"][0]
    assert segment["start"] == {"numerator": 0, "denominator": 1}
    assert segment["start_ms"] == 0
    assert segment["moments"][0] == {"position": {"numerator": 0, "denominator": 1}, "time_ms": 0}
    assert segment["moments"][-1]["time_ms"] == body["extent_ms"]
    assert scene.renderer.projections == []
    assert unauthorized.status_code == 401
    assert foreign.status_code == 404


@pytest.mark.parametrize("kind", ["note", "full", "empty", "foreign"])
def test_http_preview_subset_uses_real_projection_and_rejects_before_synthesis(
    scene: Scene, kind: str
) -> None:
    from piano_app.domain.score.document.models.material import Note, NoteCarrier
    from piano_app.domain.score.document.models.notation import Accidental
    from piano_app.domain.score.document.services.helpers import iter_leaves

    current = asyncio.run(scene.storage.get(draft_id=scene.draft_id))
    assert current is not None
    carrier = next(
        leaf.carrier
        for leaf in iter_leaves(current.document.voices[0])
        if leaf.carrier is not None and leaf.carrier.id == scene.carrier_id
    )
    assert isinstance(carrier, NoteCarrier)
    added = Note.create(
        note_carrier=carrier,
        staff=current.document.staffs[0],
        staff_step=0,
        accidental=Accidental.SHARP,
    )
    asyncio.run(scene.storage.commit(draft=current))
    body = {"carrier_id": carrier.id}
    if kind != "full":
        body["note_ids"] = [added.id] if kind == "note" else [] if kind == "empty" else ["missing"]
    with TestClient(scene.app) as client:
        response = client.post(
            f"/drafts/{scene.draft_id}/playback/preview",
            headers={"Authorization": "Bearer owner"},
            json=body,
        )
    assert response.status_code == (422 if kind in ("empty", "foreign") else 200)
    if kind in ("empty", "foreign"):
        assert not scene.renderer.projections
    else:
        notes = scene.renderer.projections[0].notes
        assert len(notes) == (1 if kind == "note" else 2)
        assert notes[-1].pitch == 65
        assert all(n.end_ms == 650 and n.velocity == 31 for n in notes)


def test_bootstrap_registers_routes_and_exposes_audio_headers() -> None:
    from pydantic import SecretStr

    from piano_app.bootstrap.container import build_app
    from piano_app.bootstrap.settings.models import Settings

    app = build_app(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test:test@127.0.0.1/test",
            JWT_SECRET=SecretStr("t" * 64),
            GOOGLE_CLIENT_IDS=("test-client",),
            CORS_ORIGINS=("https://piano.test",),
            PLAYBACK_SOUNDFONT=None,
        )
    )
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        assert "/drafts/{draft_id}/playback" in schema["paths"]
        assert "/drafts/{draft_id}/playback/preview" in schema["paths"]
        assert "/drafts/{draft_id}/playback/map" in schema["paths"]
        response = client.get("/openapi.json", headers={"Origin": "https://piano.test"})
        assert "X-Draft-Version" in response.headers["access-control-expose-headers"]
        assert "X-Audio-Sample-Rate" in response.headers["access-control-expose-headers"]
