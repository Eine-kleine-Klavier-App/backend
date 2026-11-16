from collections.abc import Callable, Generator
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
from piano_app.application.errors import PlaybackUnavailableError, ScoreNotFoundError
from piano_app.application.ports.playback import AudioChunk
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.playback.saved_score import SavedScorePlaybackService
from piano_app.domain.score import Score
from piano_app.domain.score.document.models.context import SustainHold
from piano_app.domain.score.document.services.playback import PlaybackProjection


class RecordingRenderer:
    def __init__(self) -> None:
        self.closed = False

    def stream(
        self, *, projection: PlaybackProjection, cancelled: Callable[[], bool] | None = None
    ) -> Generator[AudioChunk]:
        try:
            yield AudioChunk(pcm=b"\x01\x00" * 40, start_frame=0, sample_rate=8000)
        finally:
            self.closed = True


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
async def test_saved_playback_access_and_real_content_version(
    public: bool, actor: str | None, allowed: bool
) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    note(document, Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=public), document=document), 7)
    renderer = RecordingRenderer()
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=renderer)
    if not allowed:
        with pytest.raises(ScoreNotFoundError):
            await service.prepare(score_id="score", viewer_id=actor, start=Fraction(0))
        repository.get_versioned.assert_not_awaited()
    else:
        prepared = await service.prepare(score_id="score", viewer_id=actor, start=Fraction(0))
        assert prepared.version == 7
        assert prepared.projection.notes
        assert prepared.renderer is renderer
    uow.commit.assert_not_awaited()
    repository.update_content.assert_not_awaited()
    repository.create.assert_not_awaited()


@pytest.mark.parametrize(
    ("public", "actor", "allowed"),
    [(True, None, True), (False, "owner", True), (False, None, False), (False, "other", False)],
)
async def test_saved_map_requires_access_but_not_a_synthesizer(
    public: bool, actor: str | None, allowed: bool
) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    note(document, Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=public), document=document), 7)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=None)
    if allowed:
        projection, version = await service.prepare_map(score_id="score", viewer_id=actor)
        assert version == 7
        assert projection.notes
    else:
        with pytest.raises(ScoreNotFoundError):
            await service.prepare_map(score_id="score", viewer_id=actor)
    uow.commit.assert_not_awaited()
    repository.update_content.assert_not_awaited()


async def test_missing_saved_snapshot_and_unconfigured_synthesis() -> None:
    _, repository, uow = _service(_meta(public=True))
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=None)
    repository.get_versioned.return_value = None
    with pytest.raises(ScoreNotFoundError):
        await service.prepare(score_id="score", viewer_id=None, start=Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=True), document=score()), 2)
    with pytest.raises(PlaybackUnavailableError):
        await service.prepare(score_id="score", viewer_id=None, start=Fraction(0))


async def test_saved_http_stream_has_saved_version_and_releases_synthesizer() -> None:
    _, repository, uow = _service(_meta(public=True))
    document = score()
    note(document, Fraction(0))
    SustainHold.create(start=anchor(document, Fraction(0)), end=anchor(document, Fraction(1, 2)))
    repository.get_versioned.return_value = (Score(meta=_meta(public=True), document=document), 9)
    renderer = RecordingRenderer()
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=renderer)
    current = CurrentUserOptional(service=cast(AuthService, MagicMock(spec=AuthService)))
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_saved_playback_router(service=service, current_user_optional=current))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mapped = await client.get("/scores/score/playback/map")
        response = await client.post(
            "/scores/score/playback", json={"start": {"numerator": 0, "denominator": 1}}
        )
    assert mapped.status_code == 200
    body = mapped.json()
    assert body["version"] == 9
    assert body["notes"][0]["key_release_ms"] < body["notes"][0]["end_ms"]
    assert body["pedals"][0]["down_ms"] == 0
    assert body["pedals"][0]["up_ms"] == body["notes"][0]["end_ms"]
    assert response.status_code == 200
    assert response.headers["X-Score-Version"] == "9"
    assert "X-Draft-Version" not in response.headers
    assert response.headers["X-Audio-Format"] == "s16le"
    assert response.content == b"\x01\x00" * 40
    assert renderer.closed
    repository.create.assert_not_awaited()


async def test_private_score_without_an_owner_is_not_an_anonymous_playback() -> None:
    meta = replace(_meta(public=False), author_id=None)
    _, repository, uow = _service(meta)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=RecordingRenderer())
    with pytest.raises(ScoreNotFoundError):
        await service.prepare(score_id="score", viewer_id=None, start=Fraction(0))
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
async def test_saved_preview_map_uses_existing_preview_rules_and_access(
    public: bool, actor: str | None, allowed: bool
) -> None:
    _, repository, uow = _service(_meta(public=public))
    document = score()
    first = note(document, Fraction(0))
    second = note(document, Fraction(1, 4), staff=1)
    repository.get_versioned.return_value = (
        Score(meta=_meta(public=public), document=document),
        11,
    )
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=None)
    if allowed:
        projections, version = await service.prepare_preview_map(score_id="score", viewer_id=actor)
        assert version == 11
        assert set(projections) == {first.note_carrier.id, second.note_carrier.id}
        assert projections[first.note_carrier.id].notes[0].source_id == first.id
        assert projections[first.note_carrier.id].notes[0].key_release_ms == 650
    else:
        with pytest.raises(ScoreNotFoundError):
            await service.prepare_preview_map(score_id="score", viewer_id=actor)
        repository.get_versioned.assert_not_awaited()
    uow.commit.assert_not_awaited()
    repository.create.assert_not_awaited()
    repository.update_content.assert_not_awaited()


async def test_saved_preview_http_is_json_read_and_missing_snapshot_is_404() -> None:
    _, repository, uow = _service(_meta(public=True))
    document = score()
    first = note(document, Fraction(0))
    repository.get_versioned.return_value = (Score(meta=_meta(public=True), document=document), 11)
    service = SavedScorePlaybackService(score_uow_factory=lambda: uow, renderer=None)
    current = CurrentUserOptional(service=cast(AuthService, MagicMock(spec=AuthService)))
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(build_saved_playback_router(service=service, current_user_optional=current))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/scores/score/playback/preview/map")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        body = response.json()
        assert body["version"] == 11
        assert body["carriers"][0]["carrier_id"] == first.note_carrier.id
        assert body["carriers"][0]["notes"][0]["duration_ms"] == 650
        repository.get_versioned.return_value = None
        assert (await client.get("/scores/score/playback/preview/map")).status_code == 404
    uow.commit.assert_not_awaited()
    repository.create.assert_not_awaited()
