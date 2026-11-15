import asyncio
import struct
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from tests.unit.adapters.outbound.test_fluidsynth import FakeSession, renderer
from tests.unit.domain.document_builders import note, score

from piano_app.adapters.inbound.http.score.playback.preview_socket import (
    build_preview_socket_router,
)
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import InvalidAccessTokenError
from piano_app.application.use_cases.score.playback.preview_session import PreviewSessionService


def setup_socket():
    storage = InMemoryDraftHistory()
    document = score()
    n = note(document, Fraction(0))
    draft = asyncio.run(
        storage.create(title="socket", author_id="owner", ref_score_id=None, document=document)
    )
    native = FakeSession()
    service = PreviewSessionService(storage=storage, renderer=renderer(native, tail=100))
    auth = Mock()
    auth.authenticate_access_token.return_value = "owner"
    app = FastAPI()
    app.include_router(
        build_preview_socket_router(
            service=service, auth=auth, allowed_origins=("http://localhost:5173",)
        )
    )
    return app, service, auth, native, n, f"/drafts/{draft.draft_id}/playback/preview/live"


def connect(client, path):
    return client.websocket_connect(path, headers={"origin": "http://localhost:5173"})


def test_authenticated_preview_replacement_credit_release_and_cleanup():
    app, service, auth, native, n, path = setup_socket()
    with TestClient(app) as client, connect(client, path) as ws:
        ws.send_json({"type": "auth", "token": "valid"})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "preview", "sequence": 1, "carrier_id": n.note_carrier.id})
        format = ws.receive_json()
        assert format["type"] == "format" and format["max_buffer_frames"] == 320
        assert format["packet_sequence"] == "u64le"
        assert ws.receive_json()["type"] == "accepted"
        frames = 0
        for _ in range(4):
            packet = ws.receive_bytes()
            assert struct.unpack_from("<Q", packet)[0] == 1
            frames += (len(packet) - 8) // 4
        assert frames == 320
        ws.send_json({"type": "release", "sequence": 2})
        assert ws.receive_json()["type"] == "accepted"
        assert native.events[-1][0] == "off"
        ws.send_json({"type": "ack", "frames": frames})
        while True:
            response = ws.receive()
            if response.get("bytes") is not None:
                packet = response["bytes"]
                assert struct.unpack_from("<Q", packet)[0] == 2
                frames += (len(packet) - 8) // 4
                ws.send_json({"type": "ack", "frames": frames})
            else:
                import json

                payload = json.loads(response["text"])
                if payload["type"] == "idle":
                    assert payload["sequence"] == 2 and payload["frames"] == frames
                    break
        assert frames == 1120  # Credit window + the natural 100ms release, no hard cut.
    assert native.closed
    assert not service._sessions
    assert auth.authenticate_access_token.call_count > 2


@pytest.mark.parametrize("case", ["origin", "token", "foreign"])
def test_bad_origin_token_and_draft_access_are_refused(case):
    app, service, auth, native, _, path = setup_socket()
    if case == "token":
        auth.authenticate_access_token.side_effect = InvalidAccessTokenError()
    if case == "foreign":
        auth.authenticate_access_token.return_value = "other"
    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as error,
            client.websocket_connect(
                path,
                headers={
                    "origin": "https://other.example"
                    if case == "origin"
                    else "http://localhost:5173"
                },
            ) as ws,
        ):
            ws.send_json({"type": "auth", "token": "bad"})
            ws.receive_json()
        assert error.value.code == {"origin": 4403, "token": 4401, "foreign": 4404}[case]
    assert not service._sessions
    assert not native.events


def test_invalid_credit_is_rejected_and_invalid_commands_do_not_allocate():
    app, service, _, native, _, path = setup_socket()
    with TestClient(app) as client, connect(client, path) as ws:
        ws.send_json({"type": "auth", "token": "valid"})
        ws.receive_json()
        ws.send_json({"type": "preview", "sequence": True, "carrier_id": "bad"})
        assert ws.receive_json()["status"] == 422
        ws.send_json({"type": "preview", "sequence": 1, "carrier_id": "missing"})
        assert ws.receive_json()["status"] == 404
        ws.send_json({"type": "ack", "frames": 1})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4400
    assert not native.events
    assert not service._sessions
