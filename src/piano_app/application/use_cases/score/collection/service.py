from collections.abc import Sequence

from piano_app.application.errors import InvalidPaginationCursorError, ScoreNotFoundError
from piano_app.application.ports import (
    CollectionSummary,
    Page,
    PaginationCursorDecodingError,
    ScoreMetaItem,
    ScoreUoWFactory,
)
from piano_app.application.use_cases.score.shared import require_owned_collection


class CollectionService:
    """A user's private collections. Every operation is scoped to the caller: someone else's
    collection is indistinguishable from a missing one."""

    def __init__(self, *, score_uow_factory: ScoreUoWFactory) -> None:
        self._score_uow_factory: ScoreUoWFactory = score_uow_factory

    async def create(self, *, owner_id: str, name: str) -> CollectionSummary:
        async with self._score_uow_factory() as uow:
            created: CollectionSummary = await uow.collection_repository.create(
                owner_id=owner_id, name=name
            )
            await uow.commit()
        return created

    async def list_mine(self, *, owner_id: str) -> Sequence[CollectionSummary]:
        async with self._score_uow_factory() as uow:
            return await uow.collection_repository.list_owned(owner_id=owner_id)

    async def rename(self, *, collection_id: str, owner_id: str, name: str) -> None:
        async with self._score_uow_factory() as uow:
            await require_owned_collection(
                collection_repository=uow.collection_repository,
                collection_id=collection_id,
                owner_id=owner_id,
            )
            await uow.collection_repository.rename(collection_id=collection_id, name=name)
            await uow.commit()

    async def delete(self, *, collection_id: str, owner_id: str) -> None:
        async with self._score_uow_factory() as uow:
            await require_owned_collection(
                collection_repository=uow.collection_repository,
                collection_id=collection_id,
                owner_id=owner_id,
            )
            await uow.collection_repository.delete(collection_id=collection_id)
            await uow.commit()

    async def search_scores(
        self,
        *,
        collection_id: str,
        owner_id: str,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> Page[ScoreMetaItem]:
        async with self._score_uow_factory() as uow:
            await require_owned_collection(
                collection_repository=uow.collection_repository,
                collection_id=collection_id,
                owner_id=owner_id,
            )
            try:
                return await uow.catalog_query.search_collection(
                    collection_id=collection_id, query=query, limit=limit, cursor=cursor
                )
            except PaginationCursorDecodingError as error:
                raise InvalidPaginationCursorError from error

    async def add_score(self, *, collection_id: str, owner_id: str, score_id: str) -> None:
        async with self._score_uow_factory() as uow:
            await require_owned_collection(
                collection_repository=uow.collection_repository,
                collection_id=collection_id,
                owner_id=owner_id,
            )
            added: bool = await uow.collection_repository.add_score(
                collection_id=collection_id, score_id=score_id, owner_id=owner_id
            )
            if not added:
                raise ScoreNotFoundError(score_id=score_id)
            await uow.commit()

    async def remove_score(self, *, collection_id: str, owner_id: str, score_id: str) -> None:
        async with self._score_uow_factory() as uow:
            await require_owned_collection(
                collection_repository=uow.collection_repository,
                collection_id=collection_id,
                owner_id=owner_id,
            )
            await uow.collection_repository.remove_score(
                collection_id=collection_id, score_id=score_id
            )
            await uow.commit()

    async def collection_ids_with_score(self, *, owner_id: str, score_id: str) -> Sequence[str]:
        async with self._score_uow_factory() as uow:
            return await uow.collection_repository.collection_ids_with_score(
                owner_id=owner_id, score_id=score_id
            )
