from collections.abc import Sequence

from sqlalchemy import ScalarResult, Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from piano_app.adapters.outbound.postgres.draft.schema import DraftContentModel, DraftMetaModel
from piano_app.application.ports.score import (
    DocumentRecord,
    DraftMeta,
    DraftStoreNotFoundError,
    StoredDraft,
)


class PostgresDraftArchive:
    """The cold tier: a whole `StoredDraft` goes in and out of durable storage. An archive write
    lands only on a version newer than the stored one, so a late write never undoes a later one."""

    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] = session_factory

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft:
        async with self._session_factory() as session:
            meta: DraftMetaModel = DraftMetaModel(
                title=title,
                author_id=author_id,
                score_id=ref_score_id,
            )
            session.add(meta)
            await session.flush()

            content: DraftContentModel = DraftContentModel(
                id=meta.id,
                record=record,
                changes=[],
                cursor=0,
                version=0,
            )
            session.add(content)

            # built before commit: commit() may expire meta/content's attributes
            stored: StoredDraft = self._to_stored(meta=meta, content=content)
            await session.commit()

        return stored

    async def delete(self, *, draft_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(DraftMetaModel).where(DraftMetaModel.id == draft_id))
            await session.commit()

    async def archive(self, *, draft: StoredDraft) -> None:
        async with self._session_factory() as session:
            updated_content_id: str | None = await session.scalar(
                update(DraftContentModel)
                .where(
                    DraftContentModel.id == draft.meta.draft_id,
                    DraftContentModel.version < draft.version,
                )
                .values(
                    record=draft.record,
                    changes=list(draft.changes),
                    cursor=draft.cursor,
                    version=draft.version,
                )
                .returning(DraftContentModel.id)
            )
            if updated_content_id is not None:
                await session.execute(
                    update(DraftMetaModel)
                    .where(DraftMetaModel.id == draft.meta.draft_id)
                    .values(updated_at=func.now())
                )
                await session.commit()
                return

            # check if the draft is non-existent or simply a version has already moved forward
            stored_id: str | None = await session.scalar(
                select(DraftMetaModel.id).where(DraftMetaModel.id == draft.meta.draft_id)
            )
            if stored_id is None:
                raise DraftStoreNotFoundError(draft_id=draft.meta.draft_id)

    async def get(self, *, draft_id: str) -> StoredDraft | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(DraftMetaModel, DraftContentModel)
                .join(DraftContentModel, DraftContentModel.id == DraftMetaModel.id)
                .where(DraftMetaModel.id == draft_id)
            )
            row = result.one_or_none()
            if row is None:
                return None

            return self._to_stored(meta=row[0], content=row[1])

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        async with self._session_factory() as session:
            statement: Select[DraftMetaModel] = (
                select(DraftMetaModel)
                .where(DraftMetaModel.author_id == author_id)
                .order_by(DraftMetaModel.updated_at.desc(), DraftMetaModel.id.desc())
            )
            result: ScalarResult[DraftMetaModel] = await session.scalars(statement)
            return [row.to_meta() for row in result.all()]

    @staticmethod
    def _to_stored(*, meta: DraftMetaModel, content: DraftContentModel) -> StoredDraft:
        return StoredDraft(
            meta=meta.to_meta(),
            version=content.version,
            record=content.record,
            changes=tuple(content.changes),
            cursor=content.cursor,
        )
