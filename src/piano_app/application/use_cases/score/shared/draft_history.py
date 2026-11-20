from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from piano_app.application.ports.score import (
    DocumentCodec,
    DocumentRecord,
    DraftMeta,
    DraftStorage,
    RecordChange,
    RecordStep,
    StoredDraft,
    VersionedDraftDocument,
)
from piano_app.application.use_cases.score.shared.record_patch import (
    apply_change,
    diff_records,
    inverted,
)
from piano_app.domain.score.document import ScoreDocument


class DraftHistoryService:
    """The drafts with their undo and redo, kept in a ``DraftStorage``.

    The storage holds the current record and one change per gesture (at most
    ``max_history_size`` of them); undo takes the latest applied change back and redo applies it
    again. A commit writes the change between the record the draft was loaded as and the
    document's record now.
    """

    def __init__(
        self,
        *,
        storage: DraftStorage,
        codec: DocumentCodec,
        max_history_size: int = 30,
    ) -> None:
        if max_history_size < 1:
            raise ValueError(f"max_history_size must be >= 1, got {max_history_size!r}.")

        self._storage: DraftStorage = storage
        self._codec: DocumentCodec = codec
        self._max_history_size: int = max_history_size

    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        document: ScoreDocument,
    ) -> VersionedDraftDocument:
        stored: StoredDraft = await self._storage.create(
            title=title,
            author_id=author_id,
            ref_score_id=ref_score_id,
            record=self._codec.serialize(document),
        )

        return VersionedDraftDocument(stored=stored, document=document)

    async def get(self, *, draft_id: str) -> VersionedDraftDocument | None:
        stored: StoredDraft | None = await self._storage.get(draft_id=draft_id)
        if stored is None:
            return None

        return VersionedDraftDocument(
            stored=stored, document=self._codec.deserialize(stored.record)
        )

    async def delete(self, *, draft_id: str) -> None:
        await self._storage.delete(draft_id=draft_id)

    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        return await self._storage.list_by_author(author_id=author_id)

    async def commit(self, *, draft: VersionedDraftDocument) -> RecordStep:
        stored: StoredDraft = draft.stored
        record: DocumentRecord = self._codec.serialize(draft.document)
        change: RecordChange = diff_records(before=stored.record, after=record)

        # a gesture after an undo cuts off the changes that were left ahead
        changes: tuple[RecordChange, ...] = (*stored.changes[: stored.cursor], change)
        changes = changes[-self._max_history_size :]

        await self._write(stored=stored, record=record, changes=changes, cursor=len(changes))

        return RecordStep(
            before=stored.record,
            change=change,
            from_version=stored.version,
            to_version=stored.version + 1,
        )

    async def undo(self, *, draft: VersionedDraftDocument) -> RecordStep | None:
        stored: StoredDraft = draft.stored
        if stored.cursor == 0:
            return None

        change: RecordChange = inverted(change=stored.changes[stored.cursor - 1])
        record: DocumentRecord = apply_change(record=stored.record, change=change, forward=True)
        await self._write(
            stored=stored, record=record, changes=stored.changes, cursor=stored.cursor - 1
        )

        return RecordStep(
            before=stored.record,
            change=change,
            from_version=stored.version,
            to_version=stored.version + 1,
        )

    async def redo(self, *, draft: VersionedDraftDocument) -> RecordStep | None:
        stored: StoredDraft = draft.stored
        if stored.cursor == len(stored.changes):
            return None

        change: RecordChange = stored.changes[stored.cursor]
        record: DocumentRecord = apply_change(record=stored.record, change=change, forward=True)
        await self._write(
            stored=stored, record=record, changes=stored.changes, cursor=stored.cursor + 1
        )

        return RecordStep(
            before=stored.record,
            change=change,
            from_version=stored.version,
            to_version=stored.version + 1,
        )

    async def _write(
        self,
        *,
        stored: StoredDraft,
        record: DocumentRecord,
        changes: tuple[RecordChange, ...],
        cursor: int,
    ) -> None:
        await self._storage.put(
            draft=StoredDraft(
                meta=replace(stored.meta, updated_at=datetime.now(UTC)),
                version=stored.version + 1,
                record=record,
                changes=changes,
                cursor=cursor,
            ),
            expected_version=stored.version,
        )
