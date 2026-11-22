import asyncio
import time
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fixtures.drafts import in_memory_history
from tests.unit.application.test_import_service import _SCORE

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.import_score import build_import_router
from piano_app.adapters.outbound.importers.musicxml.reader import MusicXmlReader
from piano_app.application.errors import InvalidAccessTokenError
from piano_app.application.use_cases.score.import_score.builder import ScoreBuilder
from piano_app.application.use_cases.score.import_score.compare import ScoreComparer
from piano_app.application.use_cases.score.import_score.jobs import ImportJobs
from piano_app.application.use_cases.score.import_score.service import ImportService
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

_OWNER = {"Authorization": "Bearer owner"}
_OTHER = {"Authorization": "Bearer other"}


@pytest.fixture
def storage() -> DraftHistoryService:
    return in_memory_history()


def _app(storage: DraftHistoryService, *, max_upload_bytes: int = 100_000) -> FastAPI:
    auth = Mock()

    def authenticate(*, token: str | None) -> str:
        if token not in ("owner", "other"):
            raise InvalidAccessTokenError()
        return token

    auth.authenticate_access_token.side_effect = authenticate
    service = ImportService(
        storage=storage,
        readers=(MusicXmlReader(),),
        builder=ScoreBuilder(engine=build_engine(), compiler=build_compiler()),
        comparer=ScoreComparer(),
        jobs=ImportJobs(),
    )
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_import_router(
            service=service,
            current_user=CurrentUser(service=auth),
            max_upload_bytes=max_upload_bytes,
        )
    )
    return app


def test_an_upload_starts_a_job_that_ends_with_a_draft_and_the_report(
    storage: DraftHistoryService,
) -> None:
    with TestClient(_app(storage)) as client:
        started = client.post("/imports?filename=etude.musicxml", content=_SCORE, headers=_OWNER)
        assert started.status_code == 202
        job_id = started.json()["job_id"]
        assert started.headers["location"] == f"/imports/{job_id}"
        for _ in range(500):
            body = client.get(f"/imports/{job_id}", headers=_OWNER).json()
            if body["state"] in ("done", "failed"):
                break
            time.sleep(0.01)

    assert body["state"] == "done"
    assert body["error"] is None
    assert body["comparison"] == [
        {
            "kind": "skipped",
            "measure_index": 0,
            "onset": {"numerator": 0, "denominator": 1},
            "message": "<words> is not imported.",
        }
    ]
    draft = asyncio.run(storage.get(draft_id=body["draft_id"]))
    assert draft is not None and draft.meta.title == "Etude"


def test_a_refused_file_is_a_failed_job_with_its_reason(storage: DraftHistoryService) -> None:
    with TestClient(_app(storage)) as client:
        job_id = client.post("/imports?filename=x.xml", content=b"<no", headers=_OWNER).json()[
            "job_id"
        ]
        for _ in range(500):
            body = client.get(f"/imports/{job_id}", headers=_OWNER).json()
            if body["state"] in ("done", "failed"):
                break
            time.sleep(0.01)

    assert (body["state"], body["error"], body["draft_id"]) == (
        "failed",
        "The file is not readable MusicXML.",
        None,
    )


def test_what_the_api_refuses_before_a_job_starts(storage: DraftHistoryService) -> None:
    with TestClient(_app(storage, max_upload_bytes=50)) as client:
        assert client.post("/imports?filename=a.xml", content=b"<a/>").status_code == 401
        assert client.post("/imports", content=b"<a/>", headers=_OWNER).status_code == 422
        assert (
            client.post("/imports?filename=a.pdf", content=b"%PDF", headers=_OWNER).status_code
            == 415
        )
        assert (
            client.post(
                "/imports?filename=a.xml", content=b"<" + b"a" * 100, headers=_OWNER
            ).status_code
            == 413
        )


def test_a_job_is_not_visible_to_another_user(storage: DraftHistoryService) -> None:
    with TestClient(_app(storage)) as client:
        job_id = client.post(
            "/imports?filename=etude.musicxml", content=_SCORE, headers=_OWNER
        ).json()["job_id"]
        assert client.get(f"/imports/{job_id}", headers=_OTHER).status_code == 404
        assert client.get("/imports/missing", headers=_OWNER).status_code == 404
        assert client.get(f"/imports/{job_id}").status_code == 401


def test_a_draft_is_compared_with_a_file_on_request(storage: DraftHistoryService) -> None:
    other = _SCORE.replace(b"<step>C</step>", b"<step>D</step>")
    with TestClient(_app(storage)) as client:
        imported = client.post("/imports?filename=etude.musicxml", content=_SCORE, headers=_OWNER)
        for _ in range(500):
            first = client.get(f"/imports/{imported.json()['job_id']}", headers=_OWNER).json()
            if first["state"] in ("done", "failed"):
                break
            time.sleep(0.01)
        draft_id = first["draft_id"]
        assert (
            client.post(
                f"/drafts/{draft_id}/compare?filename=a.musicxml", content=other, headers=_OTHER
            ).status_code
            == 404
        )
        started = client.post(
            f"/drafts/{draft_id}/compare?filename=a.musicxml", content=other, headers=_OWNER
        )
        assert started.status_code == 202
        for _ in range(500):
            body = client.get(f"/imports/{started.json()['job_id']}", headers=_OWNER).json()
            if body["state"] in ("done", "failed"):
                break
            time.sleep(0.01)

    assert body["draft_id"] == draft_id
    assert [(i["kind"], i["measure_index"]) for i in body["comparison"]] == [
        ("skipped", 0),
        ("mismatch", 0),
        ("mismatch", 0),
    ]
