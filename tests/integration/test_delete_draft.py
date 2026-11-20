"""Opt-in isolated PostgreSQL check; all test DDL/data are rolled back."""

import os
from dataclasses import replace
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
                archive = PostgresDraftArchive(session_factory=factory)
                record = ScoreDocumentCodec().serialize(
                    ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=2)
                )
                first = await archive.create(
                    title="Delete", author_id="owner", ref_score_id="saved", record=record
                )
                second = await archive.create(
                    title="Keep", author_id="owner", ref_score_id=None, record=record
                )
                await archive.delete(draft_id=first.meta.draft_id)
                await archive.delete(draft_id=first.meta.draft_id)
                assert await archive.get(draft_id=first.meta.draft_id) is None
                remaining = await archive.list_by_author(author_id="owner")
                assert [meta.draft_id for meta in remaining] == [second.meta.draft_id]
                async with factory() as session:
                    assert await session.get(DraftContentModel, first.meta.draft_id) is None
                with pytest.raises(DraftStoreNotFoundError):
                    await archive.archive(draft=first)
                assert await archive.get(draft_id=first.meta.draft_id) is None
                assert await archive.get(draft_id=second.meta.draft_id) is not None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def test_an_archive_write_lands_only_on_a_newer_version() -> None:
    url = os.environ.get("PIANO_TEST_DRAFT_DATABASE_URL")
    if not url:
        pytest.skip("Set PIANO_TEST_DRAFT_DATABASE_URL for the isolated Postgres check")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = "draft_archive_" + uuid4().hex
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                await connection.run_sync(DraftBase.metadata.create_all)
                factory = async_sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                archive = PostgresDraftArchive(session_factory=factory)
                created = await archive.create(
                    title="Draft", author_id="owner", ref_score_id=None, record={"tables": {}}
                )
                change = {"fields": {"music_revision": ["a", "b"]}}
                newer = replace(
                    created,
                    version=2,
                    record={"music_revision": "b", "tables": {}},
                    changes=(change,),
                    cursor=1,
                )

                await archive.archive(draft=newer)
                await archive.archive(draft=replace(created, version=1))

                stored = await archive.get(draft_id=created.meta.draft_id)
                assert stored is not None
                assert (stored.version, stored.record, stored.changes, stored.cursor) == (
                    2,
                    newer.record,
                    (change,),
                    1,
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
