from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock, call, create_autospec

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from piano_app.adapters.inbound.http import CurrentUser, register_exception_handlers
from piano_app.adapters.inbound.http.score.collection.requests import CollectionNameRequest
from piano_app.adapters.inbound.http.score.collection.router import build_collection_router
from piano_app.application.errors import (
    CollectionNotFoundError,
    InvalidPaginationCursorError,
    ScoreNotFoundError,
)
from piano_app.application.ports import PaginationCursorDecodingError
from piano_app.application.ports.score import (
    CollectionPin,
    CollectionRepository,
    CollectionSummary,
    ScoreCatalogQuery,
    ScoreRepository,
    ScoreUoW,
)
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.collection.service import CollectionService
from piano_app.application.use_cases.score.manage.service import ScoreManageService
from piano_app.domain.score import Score, ScoreMeta


def _meta(*, public: bool, author: str = "author") -> ScoreMeta:
    now = datetime.now(UTC)
    return ScoreMeta(
        id="score",
        title="Etude",
        composer="Chopin",
        author_id=author,
        is_public=public,
        created_at=now,
        updated_at=now,
    )


def _uow(*, owned: bool = True, meta: ScoreMeta | None = None) -> MagicMock:
    collections: MagicMock = create_autospec(CollectionRepository, instance=True)
    collections.get_owned.return_value = (
        CollectionSummary(id="collection", name="Etudes", score_count=0) if owned else None
    )
    collections.pins_of_other_owners.return_value = []
    scores: MagicMock = create_autospec(ScoreRepository, instance=True)
    scores.get_meta.return_value = meta
    uow: MagicMock = create_autospec(ScoreUoW, instance=True)
    uow.collection_repository = collections
    uow.score_repository = scores
    uow.catalog_query = create_autospec(ScoreCatalogQuery, instance=True)
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = False
    return uow


def _collections(uow: MagicMock) -> CollectionService:
    return CollectionService(score_uow_factory=lambda: cast(ScoreUoW, uow))


async def test_create_commits_the_new_collection() -> None:
    uow = _uow()
    uow.collection_repository.create.return_value = CollectionSummary(
        id="collection", name="Etudes", score_count=0
    )

    created = await _collections(uow).create(owner_id="anna", name="Etudes")

    assert created.id == "collection"
    uow.collection_repository.create.assert_awaited_once_with(owner_id="anna", name="Etudes")
    uow.commit.assert_awaited_once_with()


@pytest.mark.parametrize("operation", ["rename", "delete", "search", "add", "remove"])
async def test_someone_elses_collection_is_not_found_and_nothing_is_written(
    operation: str,
) -> None:
    uow = _uow(owned=False, meta=_meta(public=True))
    service = _collections(uow)

    with pytest.raises(CollectionNotFoundError):
        match operation:
            case "rename":
                await service.rename(collection_id="collection", owner_id="bob", name="New")
            case "delete":
                await service.delete(collection_id="collection", owner_id="bob")
            case "search":
                await service.search_scores(
                    collection_id="collection", owner_id="bob", query=None, limit=10, cursor=None
                )
            case "add":
                await service.add_score(
                    collection_id="collection", owner_id="bob", score_id="score"
                )
            case _:
                await service.remove_score(
                    collection_id="collection", owner_id="bob", score_id="score"
                )

    uow.commit.assert_not_awaited()
    uow.catalog_query.search_collection.assert_not_awaited()


@pytest.mark.parametrize("readable", [True, False])
async def test_adding_depends_on_the_repository_confirming_the_score_is_readable(
    readable: bool,
) -> None:
    uow = _uow()
    uow.collection_repository.add_score.return_value = readable
    service = _collections(uow)

    if readable:
        await service.add_score(collection_id="collection", owner_id="anna", score_id="score")
        uow.commit.assert_awaited_once_with()
    else:
        with pytest.raises(ScoreNotFoundError):
            await service.add_score(collection_id="collection", owner_id="anna", score_id="score")
        uow.commit.assert_not_awaited()

    uow.collection_repository.add_score.assert_awaited_once_with(
        collection_id="collection", score_id="score", owner_id="anna"
    )


async def test_a_bad_cursor_is_an_application_error() -> None:
    uow = _uow()
    uow.catalog_query.search_collection.side_effect = PaginationCursorDecodingError()

    with pytest.raises(InvalidPaginationCursorError):
        await _collections(uow).search_scores(
            collection_id="collection", owner_id="anna", query=None, limit=10, cursor="bad"
        )


async def test_hiding_a_score_nobody_saved_makes_no_copies() -> None:
    uow = _uow(meta=_meta(public=True))
    service = ScoreManageService(score_uow_factory=lambda: cast(ScoreUoW, uow))

    await service.update_visibility(score_id="score", actor_id="author", is_public=False)

    uow.score_repository.create.assert_not_awaited()
    uow.collection_repository.repin.assert_not_awaited()
    uow.commit.assert_awaited_once_with()


async def test_hiding_a_score_gives_each_holder_a_private_copy_of_their_version() -> None:
    uow = _uow(meta=_meta(public=True))
    uow.collection_repository.pins_of_other_owners.return_value = [
        CollectionPin(item_id="i1", owner_id="anna", score_content_id="c1"),
        CollectionPin(item_id="i2", owner_id="anna", score_content_id="c1"),
        CollectionPin(item_id="i3", owner_id="bob", score_content_id="c2"),
    ]
    uow.score_repository.get_content_document.side_effect = lambda *, content_id: MagicMock(
        name=content_id
    )
    created: list[str] = ["copy-anna", "copy-bob"]
    uow.score_repository.create.side_effect = lambda **_: cast(Score, MagicMock(id=created.pop(0)))
    service = ScoreManageService(score_uow_factory=lambda: cast(ScoreUoW, uow))

    await service.update_visibility(score_id="score", actor_id="author", is_public=False)

    assert uow.score_repository.create.await_count == 2
    first = uow.score_repository.create.await_args_list[0].kwargs
    assert first["author_id"] == "anna"
    assert first["title"] == "Etude"
    assert first["derived_from_id"] == "score"
    assert "is_public" not in first  # a copy stays private
    assert uow.collection_repository.repin.await_args_list == [
        call(item_id="i1", score_id="copy-anna"),
        call(item_id="i2", score_id="copy-anna"),
        call(item_id="i3", score_id="copy-bob"),
    ]
    uow.commit.assert_awaited_once_with()


async def test_publishing_a_score_never_looks_for_holders() -> None:
    uow = _uow(meta=_meta(public=False))
    service = ScoreManageService(score_uow_factory=lambda: cast(ScoreUoW, uow))

    await service.update_visibility(score_id="score", actor_id="author", is_public=True)

    uow.collection_repository.pins_of_other_owners.assert_not_awaited()


@pytest.mark.parametrize("name", ["", "   "])
def test_a_collection_needs_a_name(name: str) -> None:
    with pytest.raises(ValidationError):
        CollectionNameRequest(name=name)


def test_a_collection_name_is_trimmed() -> None:
    assert CollectionNameRequest(name="  Etudes ").name == "Etudes"


async def test_route_maps_a_missing_collection_to_404() -> None:
    uow = _uow(owned=False)
    current_user = CurrentUser(service=cast(AuthService, MagicMock(spec=AuthService)))

    async def authenticated_actor() -> str:
        return "bob"

    app = FastAPI()
    register_exception_handlers(app=app)
    app.dependency_overrides[current_user] = authenticated_actor
    app.include_router(
        build_collection_router(service=_collections(uow), current_user=current_user)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/collections/collection")

    assert response.status_code == 404
    uow.commit.assert_not_awaited()
