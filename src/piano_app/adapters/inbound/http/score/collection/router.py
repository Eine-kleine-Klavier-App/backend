from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.pagination import DEFAULT_LIMIT, MAX_LIMIT, PageResponse
from piano_app.application.ports import CollectionSummary, Page, ScoreMetaItem
from piano_app.application.use_cases.score.collection.service import CollectionService

from ..catalog.responses import ScoreCardResponse
from .requests import CollectionNameRequest
from .responses import CollectionResponse, ScoreCollectionsResponse


def build_collection_router(*, service: CollectionService, current_user: CurrentUser) -> APIRouter:
    router: APIRouter = APIRouter(tags=["collections"])

    @router.post(path="/collections", status_code=201)
    async def create_collection(
        owner_id: Annotated[str, Depends(current_user)],
        request: CollectionNameRequest,
    ) -> CollectionResponse:
        created: CollectionSummary = await service.create(owner_id=owner_id, name=request.name)
        return CollectionResponse.from_summary(created)

    @router.get(path="/collections", status_code=200)
    async def list_collections(
        owner_id: Annotated[str, Depends(current_user)],
    ) -> list[CollectionResponse]:
        collections: Sequence[CollectionSummary] = await service.list_mine(owner_id=owner_id)
        return [CollectionResponse.from_summary(collection) for collection in collections]

    @router.patch(path="/collections/{collection_id}", status_code=204)
    async def rename_collection(
        collection_id: Annotated[str, Path(description="The collection ID")],
        owner_id: Annotated[str, Depends(current_user)],
        request: CollectionNameRequest,
    ) -> None:
        await service.rename(collection_id=collection_id, owner_id=owner_id, name=request.name)

    @router.delete(path="/collections/{collection_id}", status_code=204)
    async def delete_collection(
        collection_id: Annotated[str, Path(description="The collection ID")],
        owner_id: Annotated[str, Depends(current_user)],
    ) -> None:
        await service.delete(collection_id=collection_id, owner_id=owner_id)

    @router.get(path="/collections/{collection_id}/scores", status_code=200)
    async def search_collection_scores(
        collection_id: Annotated[str, Path(description="The collection ID")],
        owner_id: Annotated[str, Depends(current_user)],
        q: Annotated[str | None, Query(description="Search over title and composer")] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
        cursor: Annotated[
            str | None,
            Query(description="Opaque page cursor from a previous page's next_cursor"),
        ] = None,
    ) -> PageResponse[ScoreCardResponse]:
        page: Page[ScoreMetaItem] = await service.search_scores(
            collection_id=collection_id,
            owner_id=owner_id,
            query=q,
            limit=limit,
            cursor=cursor,
        )
        return PageResponse.of(page, item=ScoreCardResponse.from_item)

    @router.put(path="/collections/{collection_id}/scores/{score_id}", status_code=204)
    async def add_score_to_collection(
        collection_id: Annotated[str, Path(description="The collection ID")],
        score_id: Annotated[str, Path(description="The score ID")],
        owner_id: Annotated[str, Depends(current_user)],
    ) -> None:
        await service.add_score(collection_id=collection_id, owner_id=owner_id, score_id=score_id)

    @router.delete(path="/collections/{collection_id}/scores/{score_id}", status_code=204)
    async def remove_score_from_collection(
        collection_id: Annotated[str, Path(description="The collection ID")],
        score_id: Annotated[str, Path(description="The score ID")],
        owner_id: Annotated[str, Depends(current_user)],
    ) -> None:
        await service.remove_score(
            collection_id=collection_id, owner_id=owner_id, score_id=score_id
        )

    @router.get(path="/scores/{score_id}/collections", status_code=200)
    async def get_score_collections(
        score_id: Annotated[str, Path(description="The score ID")],
        owner_id: Annotated[str, Depends(current_user)],
    ) -> ScoreCollectionsResponse:
        collection_ids: Sequence[str] = await service.collection_ids_with_score(
            owner_id=owner_id, score_id=score_id
        )
        return ScoreCollectionsResponse.from_ids(collection_ids)

    return router
