from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.unit.application.test_score_visibility import _meta, _service
from tests.unit.domain.document_builders import score

from piano_app.adapters.inbound.http import CurrentUser, register_exception_handlers
from piano_app.adapters.inbound.http.score.manage.router import build_manage_router
from piano_app.application.contracts.score import CreateScoreCommand
from piano_app.application.errors import ScoreNotFoundError, ScoreNotOwnedError
from piano_app.application.use_cases.auth import AuthService
from piano_app.domain.score import Score


async def test_metadata_changes_only_metadata() -> None:
    service, repository, uow = _service(_meta(public=False))
    await service.update_metadata(
        score_id="score", actor_id="owner", title="New title", composer=None
    )
    repository.set_title.assert_awaited_once_with(score_id="score", title="New title")
    repository.set_composer.assert_awaited_once_with(score_id="score", composer=None)
    repository.update_content.assert_not_awaited()
    uow.commit.assert_awaited_once_with()


@pytest.mark.parametrize("public", [True, False])
async def test_foreign_metadata_cannot_be_changed(public: bool) -> None:
    service, repository, uow = _service(_meta(public=public))
    with pytest.raises(ScoreNotOwnedError if public else ScoreNotFoundError):
        await service.update_metadata(
            score_id="score", actor_id="other", title="Changed", composer="Somebody"
        )
    repository.set_title.assert_not_awaited()
    repository.set_composer.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_second_metadata_write_failure_cannot_commit_partial_change() -> None:
    service, repository, uow = _service(_meta(public=False))
    repository.set_composer.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        await service.update_metadata(
            score_id="score", actor_id="owner", title="Changed", composer=None
        )
    uow.commit.assert_not_awaited()


@pytest.mark.parametrize("public", [True, False])
@pytest.mark.parametrize("frozen", [True, False])
async def test_saved_branch_copies_canon_with_explicit_privacy(public: bool, frozen: bool) -> None:
    service, repository, uow = _service(None)
    parent = Score(
        meta=replace(_meta(public=True), author_id=None if frozen else "owner"), document=score()
    )
    repository.get.return_value = parent
    repository.create.return_value = Score(
        meta=replace(_meta(public=public), id="new"), document=parent.document
    )
    created = await service.create_branch_from_saved(
        score_id="score",
        actor_id="other",
        command=CreateScoreCommand(title="My version", composer=None, is_public=public),
    )
    assert created == "new"
    repository.create.assert_awaited_once_with(
        title="My version",
        composer=None,
        author_id="other",
        document=parent.document,
        derived_from_id=None if frozen else "score",
        is_public=public,
    )
    repository.update_content.assert_not_awaited()
    uow.commit.assert_awaited_once_with()


async def test_private_canon_cannot_be_branched_by_another_person() -> None:
    service, repository, uow = _service(None)
    repository.get.return_value = Score(meta=_meta(public=False), document=score())
    with pytest.raises(ScoreNotFoundError):
        await service.create_branch_from_saved(
            score_id="score",
            actor_id="other",
            command=CreateScoreCommand(title="Copy", composer=None, is_public=True),
        )
    repository.create.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.parametrize("title", ["", "   "])
async def test_metadata_route_rejects_empty_title_before_write(title: str) -> None:
    service, repository, _ = _service(_meta(public=False))
    current = CurrentUser(service=cast(AuthService, MagicMock(spec=AuthService)))
    app = FastAPI()
    register_exception_handlers(app=app)
    app.dependency_overrides[current] = lambda: "owner"
    app.include_router(build_manage_router(service=service, current_user=current))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/scores/score/metadata", json={"title": title, "composer": None}
        )
    assert response.status_code == 422
    repository.set_title.assert_not_awaited()
