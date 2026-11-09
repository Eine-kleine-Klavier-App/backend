from collections.abc import Sequence

from sqlalchemy import Result, Row, ScalarResult, ScalarSelect, Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from piano_app.adapters.outbound.postgres.system.schema import (
    CollectionModel,
    CollectionScoreModel,
    ScoreContentModel,
    ScoreMetaModel,
)
from piano_app.adapters.outbound.postgres.system.score.helpers.visibility import is_readable_by
from piano_app.application.ports.score.collection_repository import (
    CollectionPin,
    CollectionSummary,
)


class PostgresCollectionRepository:
    """Implements 'CollectionRepository' using Postgres."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def create(self, *, owner_id: str, name: str) -> CollectionSummary:
        collection_model: CollectionModel = CollectionModel(author_id=owner_id, name=name)
        self._session.add(collection_model)
        await self._session.flush()

        return CollectionSummary(id=collection_model.id, name=collection_model.name, score_count=0)

    async def list_owned(self, *, owner_id: str) -> Sequence[CollectionSummary]:
        statement: Select[tuple[CollectionModel, int]] = (
            self._summaries().where(CollectionModel.author_id == owner_id)
        ).order_by(func.lower(CollectionModel.name), CollectionModel.id)
        result: Result[tuple[CollectionModel, int]] = await self._session.execute(statement)

        return [self._to_summary(row=row) for row in result.all()]

    async def get_owned(self, *, collection_id: str, owner_id: str) -> CollectionSummary | None:
        statement: Select[tuple[CollectionModel, int]] = self._summaries().where(
            CollectionModel.id == collection_id,
            CollectionModel.author_id == owner_id,
        )
        result: Result[tuple[CollectionModel, int]] = await self._session.execute(statement)
        row: Row[tuple[CollectionModel, int]] | None = result.one_or_none()

        return None if row is None else self._to_summary(row=row)

    async def rename(self, *, collection_id: str, name: str) -> None:
        await self._session.execute(
            update(CollectionModel).where(CollectionModel.id == collection_id).values(name=name)
        )

    async def delete(self, *, collection_id: str) -> None:
        await self._session.execute(
            delete(CollectionModel).where(CollectionModel.id == collection_id)
        )

    async def add_score(self, *, collection_id: str, score_id: str, owner_id: str) -> bool:
        readable: Select[tuple[str]] = (
            select(ScoreMetaModel.id)
            .where(ScoreMetaModel.id == score_id, is_readable_by(viewer_id=owner_id))
            .with_for_update(read=True)
        )
        if (await self._session.scalars(readable)).first() is None:
            return False

        held: Select[tuple[str]] = (
            select(CollectionScoreModel.id)
            .join(ScoreContentModel, ScoreContentModel.id == CollectionScoreModel.score_content_id)
            .where(
                CollectionScoreModel.collection_id == collection_id,
                ScoreContentModel.score_id == score_id,
            )
        )
        if (await self._session.scalars(held)).first() is not None:
            return True

        content_id: str = await self._current_content_id(score_id=score_id)
        await self._session.execute(
            insert(CollectionScoreModel)
            .values(collection_id=collection_id, score_content_id=content_id)
            .on_conflict_do_nothing(constraint="uq_collection_scores_collection_content")
        )

        return True

    async def remove_score(self, *, collection_id: str, score_id: str) -> None:
        versions: Select[tuple[str]] = select(ScoreContentModel.id).where(
            ScoreContentModel.score_id == score_id
        )
        await self._session.execute(
            delete(CollectionScoreModel).where(
                CollectionScoreModel.collection_id == collection_id,
                CollectionScoreModel.score_content_id.in_(versions),
            )
        )

    async def collection_ids_with_score(self, *, owner_id: str, score_id: str) -> Sequence[str]:
        statement: Select[tuple[str]] = (
            select(CollectionModel.id)
            .join(CollectionScoreModel, CollectionScoreModel.collection_id == CollectionModel.id)
            .join(ScoreContentModel, ScoreContentModel.id == CollectionScoreModel.score_content_id)
            .where(
                CollectionModel.author_id == owner_id,
                ScoreContentModel.score_id == score_id,
            )
            .distinct()
        )
        result: ScalarResult[str] = await self._session.scalars(statement)

        return result.all()

    async def pins_of_other_owners(
        self, *, score_id: str, owner_id: str
    ) -> Sequence[CollectionPin]:
        statement: Select[tuple[str, str, str]] = (
            select(
                CollectionScoreModel.id,
                CollectionModel.author_id,
                CollectionScoreModel.score_content_id,
            )
            .join(CollectionModel, CollectionModel.id == CollectionScoreModel.collection_id)
            .join(ScoreContentModel, ScoreContentModel.id == CollectionScoreModel.score_content_id)
            .where(
                ScoreContentModel.score_id == score_id,
                CollectionModel.author_id != owner_id,
            )
        )
        result: Result[tuple[str, str, str]] = await self._session.execute(statement)

        return [
            CollectionPin(item_id=row[0], owner_id=row[1], score_content_id=row[2])
            for row in result.all()
        ]

    async def repin(self, *, item_id: str, score_id: str) -> None:
        content_id: str = await self._current_content_id(score_id=score_id)
        await self._session.execute(
            update(CollectionScoreModel)
            .where(CollectionScoreModel.id == item_id)
            .values(score_content_id=content_id)
        )

    async def _current_content_id(self, *, score_id: str) -> str:
        statement: Select[tuple[str]] = (
            select(ScoreContentModel.id)
            .where(ScoreContentModel.score_id == score_id)
            .order_by(ScoreContentModel.version.desc())
            .limit(1)
        )
        result: ScalarResult[str] = await self._session.scalars(statement)
        content_id: str | None = result.one_or_none()

        if content_id is None:
            raise RuntimeError(f"Score {score_id!r} has no content.")

        return content_id

    @staticmethod
    def _summaries() -> Select[tuple[CollectionModel, int]]:
        score_count: ScalarSelect[int] = (
            select(func.count())
            .where(CollectionScoreModel.collection_id == CollectionModel.id)
            .correlate(CollectionModel)
            .scalar_subquery()
        )

        return select(CollectionModel, score_count)

    @staticmethod
    def _to_summary(*, row: Row[tuple[CollectionModel, int]]) -> CollectionSummary:
        return CollectionSummary(id=row[0].id, name=row[0].name, score_count=row[1])
