from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock, create_autospec

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from piano_app.adapters.inbound.http import CurrentUser, register_exception_handlers
from piano_app.adapters.inbound.http.score.manage.router import build_manage_router
from piano_app.adapters.inbound.http.score.save.requests import CreateScoreRequest
from piano_app.application.errors import ScoreNotFoundError, ScoreNotOwnedError
from piano_app.application.ports.score import (
    CollectionRepository,
    ScoreRepository,
    ScoreRepositoryNotFoundError,
    ScoreUoW,
)
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.manage.service import ScoreManageService
from piano_app.domain.score import ScoreMeta


def _meta(*, public: bool, author: str = "owner") -> ScoreMeta:
    now = datetime.now(UTC)
    return ScoreMeta(
        id="score", title="Bibi", author_id=author, is_public=public, created_at=now, updated_at=now
    )


def _service(meta: ScoreMeta | None) -> tuple[ScoreManageService, MagicMock, MagicMock]:
    repository: MagicMock = create_autospec(ScoreRepository, instance=True)
    repository.get_meta.return_value = meta
    uow: MagicMock = create_autospec(ScoreUoW, instance=True)
    uow.score_repository = repository
    collections: MagicMock = create_autospec(CollectionRepository, instance=True)
    collections.pins_of_other_owners.return_value = []
    uow.collection_repository = collections
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    service = ScoreManageService(score_uow_factory=lambda: cast(ScoreUoW, uow))
    return service, repository, uow


@pytest.mark.parametrize("public", [True, False])
async def test_owner_changes_visibility_without_writing_content(public: bool) -> None:
    service, repository, uow = _service(_meta(public=not public))

    await service.update_visibility(score_id="score", actor_id="owner", is_public=public)

    repository.set_visibility.assert_awaited_once_with(score_id="score", is_public=public)
    uow.commit.assert_awaited_once_with()
    repository.update_content.assert_not_awaited()
    repository.create.assert_not_awaited()


@pytest.mark.parametrize(
    ("public", "error"), [(False, ScoreNotFoundError), (True, ScoreNotOwnedError)]
)
async def test_another_author_cannot_change_visibility(
    public: bool, error: type[Exception]
) -> None:
    service, repository, uow = _service(_meta(public=public))

    with pytest.raises(error):
        await service.update_visibility(score_id="score", actor_id="other", is_public=not public)

    repository.set_visibility.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_missing_score_does_not_write_or_commit() -> None:
    service, repository, uow = _service(None)

    with pytest.raises(ScoreNotFoundError):
        await service.update_visibility(score_id="score", actor_id="owner", is_public=True)

    repository.set_visibility.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_a_score_disappearing_after_access_check_is_an_application_error() -> None:
    service, repository, uow = _service(_meta(public=False))
    repository.set_visibility.side_effect = ScoreRepositoryNotFoundError(score_id="score")

    with pytest.raises(ScoreNotFoundError):
        await service.update_visibility(score_id="score", actor_id="owner", is_public=True)

    uow.commit.assert_not_awaited()


async def test_failed_visibility_write_does_not_commit() -> None:
    service, repository, uow = _service(_meta(public=False))
    repository.set_visibility.side_effect = RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await service.update_visibility(score_id="score", actor_id="owner", is_public=True)

    uow.commit.assert_not_awaited()


@pytest.mark.parametrize("body", [{"title": "Bibi"}, {"title": "Bibi", "is_public": None}])
def test_creation_requires_an_explicit_visibility_choice(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CreateScoreRequest.model_validate(body)


@pytest.mark.parametrize("public", [True, False])
def test_creation_accepts_both_explicit_choices(public: bool) -> None:
    request = CreateScoreRequest(title="Bibi", is_public=public)
    assert request.to_command().is_public is public


@pytest.mark.parametrize(
    ("actor", "public", "expected_status"),
    [("owner", False, 200), ("owner", True, 200), ("other", False, 404), ("other", True, 403)],
)
async def test_patch_route_uses_authenticated_actor_and_existing_access_policy(
    actor: str, public: bool, expected_status: int
) -> None:
    service, repository, uow = _service(_meta(public=public))
    current_user = CurrentUser(service=cast(AuthService, MagicMock(spec=AuthService)))

    async def authenticated_actor() -> str:
        return actor

    app = FastAPI()
    register_exception_handlers(app=app)
    app.dependency_overrides[current_user] = authenticated_actor
    app.include_router(build_manage_router(service=service, current_user=current_user))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/scores/score", json={"is_public": not public})

    assert response.status_code == expected_status
    if expected_status == 200:
        repository.set_visibility.assert_awaited_once_with(score_id="score", is_public=not public)
        uow.commit.assert_awaited_once_with()
    else:
        repository.set_visibility.assert_not_awaited()
        uow.commit.assert_not_awaited()
