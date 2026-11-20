"""Opt-in isolated PostgreSQL check; all test DDL/data are rolled back."""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from piano_app.adapters.outbound.postgres.draft.archive import PostgresDraftArchive
from piano_app.adapters.outbound.postgres.draft.schema import DraftBase
from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.use_cases.score.shared.record_patch import apply_change, diff_records
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure

pytestmark = pytest.mark.integration


async def test_a_change_of_a_list_of_ids_comes_back_from_jsonb_and_still_applies() -> None:
    url = os.environ.get("PIANO_TEST_DRAFT_DATABASE_URL")
    if not url:
        pytest.skip("Set PIANO_TEST_DRAFT_DATABASE_URL for the isolated Postgres check")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = "draft_changes_" + uuid4().hex
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                await connection.run_sync(DraftBase.metadata.create_all)
                factory = async_sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                archive = PostgresDraftArchive(session_factory=factory)
                codec = ScoreDocumentCodec()
                document = ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=4)
                before = codec.serialize(document)
                created = await archive.create(
                    title="Lists", author_id="owner", ref_score_id=None, record=before
                )

                document.insert_measure_after(measure=Measure.create(), after=document.measures[1])
                after = codec.serialize(document)
                change = diff_records(before=before, after=after)
                assert change["fields"]["measure_ids"]["removed"] == []
                await archive.archive(
                    draft=replace(created, version=1, record=after, changes=(change,), cursor=1)
                )

                stored = await archive.get(draft_id=created.meta.draft_id)

                assert stored is not None
                assert stored.changes == (change,)
                assert stored.record == after
                assert (
                    apply_change(record=stored.record, change=stored.changes[0], forward=False)
                    == before
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
