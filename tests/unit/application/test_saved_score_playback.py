from dataclasses import replace
from fractions import Fraction
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.unit.application.test_score_visibility import _meta, _service
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.adapters.inbound.http import CurrentUserOptional, register_exception_handlers
from piano_app.adapters.inbound.http.score.playback.saved_router import build_saved_playback_router
from piano_app.application.errors import ScoreNotFoundError
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.playback.saved_score import SavedScorePlaybackService
from piano_app.domain.score import Score
from piano_app.domain.score.document.models.context import SustainHold


@pytest.mark.parametrize(
    ("public", "actor", "allowed"),
    [(True, None, True), (False, "owner", True), (False, None, False), (False, "other", False)],
)
async def test_saved_map_requires_access(public: bool, actor: str | None, allowed: bool) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    note(document, Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=public), document=document), 7)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    if allowed:
        projection, version = await service.prepare_map(score_id="score", viewer_id=actor)
        assert version == 7
        assert projection.notes
    else:
        with pytest.raises(ScoreNotFoundError):
            await service.prepare_map(score_id="score", viewer_id=actor)
    uow.commit.assert_not_awaited()
    repository.update_content.assert_not_awaited()


async def test_missing_saved_snapshot_is_not_found() -> None:
    _, repository, uow = _service(_meta(public=True))
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    repository.get_versioned.return_value = None
    with pytest.raises(ScoreNotFoundError):
        await service.prepare_map(score_id="score", viewer_id=None)


async def test_saved_http_map_has_the_saved_version() -> None:
    _, repository, uow = _service(_meta(public=True))
    document = score()
    note(document, Fraction(0))
    SustainHold.create(start=anchor(document, Fraction(0)), end=anchor(document, Fraction(1, 2)))
    repository.get_versioned.return_value = (Score(meta=_meta(public=True), document=document), 9)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    current = CurrentUserOptional(service=cast(AuthService, MagicMock(spec=AuthService)))
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_saved_playback_router(service=service, current_user_optional=current))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mapped = await client.get("/scores/score/playback/map")
    assert mapped.status_code == 200
    body = mapped.json()
    assert body["version"] == 9
    assert body["notes"][0]["key_release_ms"] < body["notes"][0]["end_ms"]
    assert body["pedals"][0]["down_ms"] == 0
    assert body["pedals"][0]["up_ms"] == body["notes"][0]["end_ms"]
    repository.create.assert_not_awaited()


async def test_private_score_without_an_owner_is_not_an_anonymous_playback() -> None:
    meta = replace(_meta(public=False), author_id=None)
    _, repository, uow = _service(meta)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    with pytest.raises(ScoreNotFoundError):
        await service.prepare_map(score_id="score", viewer_id=None)
    repository.get_versioned.assert_not_awaited()


@pytest.mark.parametrize(
    ("public", "actor", "allowed"),
    [
        (True, None, True),
        (True, "other", True),
        (False, "owner", True),
        (False, None, False),
        (False, "other", False),
    ],
)
async def test_saved_carrier_preview_uses_existing_preview_rules_and_access(
    public: bool, actor: str | None, allowed: bool
) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    first = note(document, Fraction(0))
    note(document, Fraction(1, 4), staff=1)
    repository.get_versioned.return_value = (
        Score(meta=_meta(public=public), document=document),
        11,
    )
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    if allowed:
        projection, version = await service.prepare_preview_carrier(
            score_id="score", viewer_id=actor, carrier_id=first.note_carrier.id
        )
        assert version == 11
        assert projection.notes[0].source_id == first.id
        assert projection.notes[0].key_release_ms == 650
    else:
        with pytest.raises(ScoreNotFoundError):
            await service.prepare_preview_carrier(
                score_id="score", viewer_id=actor, carrier_id=first.note_carrier.id
            )
        repository.get_versioned.assert_not_awaited()
    uow.commit.assert_not_awaited()
    repository.create.assert_not_awaited()
    repository.update_content.assert_not_awaited()


async def test_saved_preview_http_is_json_read_and_missing_snapshot_is_404() -> None:
    _, repository, uow = _service(_meta(public=True))
    document = score()
    first = note(document, Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=True), document=document), 11)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow)
    current = CurrentUserOptional(service=cast(AuthService, MagicMock(spec=AuthService)))
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_saved_playback_router(service=service, current_user_optional=current))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        url = f"/scores/score/playback/preview/carriers/{first.note_carrier.id}"
        response = await client.get(url)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        body = response.json()
        assert (body["version"], body["carrier_id"]) == (11, first.note_carrier.id)
        assert body["notes"][0]["duration_ms"] == 650
        repository.get_versioned.return_value = None
        assert (await client.get(url)).status_code == 404
    uow.commit.assert_not_awaited()
    repository.create.assert_not_awaited()
