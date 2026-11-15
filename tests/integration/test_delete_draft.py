"""Opt-in isolated PostgreSQL check; all test DDL/data are rolled back."""

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from piano_app.adapters.outbound.postgres.draft.archive import PostgresDraftArchive
from piano_app.adapters.outbound.postgres.draft.schema import DraftBase, DraftContentModel
from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.ports.score import DraftStoreNotFoundError
from piano_app.domain.score.document import ScoreDocument

pytestmark = pytest.mark.integration


async def test_delete_cascades_and_late_archive_cannot_restore() -> None:
    url = os.environ.get("PIANO_TEST_DRAFT_DATABASE_URL")
    if not url:
        pytest.skip("Set PIANO_TEST_DRAFT_DATABASE_URL for the isolated Postgres check")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = "draft_delete_" + uuid4().hex
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                await connection.run_sync(DraftBase.metadata.create_all)
                factory = async_sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                archive = PostgresDraftArchive(session_factory=factory, codec=ScoreDocumentCodec())
                document = ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=2)
                first = await archive.create(
                    title="Delete", author_id="owner", ref_score_id="saved", document=document
                )
                second = await archive.create(
                    title="Keep", author_id="owner", ref_score_id=None, document=document
                )
                await archive.delete(draft_id=first.draft_id)
                await archive.delete(draft_id=first.draft_id)
                assert await archive.get_snapshot(draft_id=first.draft_id) is None
                remaining = await archive.list_by_author(author_id="owner")
                assert [meta.draft_id for meta in remaining] == [second.draft_id]
                async with factory() as session:
                    assert await session.get(DraftContentModel, first.draft_id) is None
                with pytest.raises(DraftStoreNotFoundError):
                    await archive.archive(snapshot=first)
                assert await archive.get_snapshot(draft_id=first.draft_id) is None
                assert await archive.get_snapshot(draft_id=second.draft_id) is not None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
