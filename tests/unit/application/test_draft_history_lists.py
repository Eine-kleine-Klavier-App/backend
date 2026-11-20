import json
from collections.abc import Callable
from fractions import Fraction

import pytest
from tests.unit.domain.scene import Score, build_engine, build_score, note_at, quarters

from piano_app.adapters.outbound.in_memory.draft_storage import InMemoryDraftStorage
from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.ports.score import DocumentRecord, StoredDraft, VersionedDraftDocument
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    EditIntent,
    TieNotesIntent,
)

# The history of a real score, whose ties live in a list of ids that every gesture on them
# changes: each state is read back exactly after undo and redo, and what the store holds for a
# gesture is a few ids, not the whole list.

_CODEC: ScoreDocumentCodec = ScoreDocumentCodec()


class _Fixture:
    def __init__(self) -> None:
        self.storage: InMemoryDraftStorage = InMemoryDraftStorage()
        self.history: DraftHistoryService = DraftHistoryService(
            storage=self.storage, codec=_CODEC, max_history_size=30
        )
        self.draft_id: str = ""

    async def create(self, *, score: Score) -> None:
        created: VersionedDraftDocument = await self.history.create(
            title="Draft", author_id="author", ref_score_id=None, document=score.document
        )
        self.draft_id = created.draft_id

    async def loaded(self) -> VersionedDraftDocument:
        loaded: VersionedDraftDocument | None = await self.history.get(draft_id=self.draft_id)
        assert loaded is not None

        return loaded

    async def record(self) -> DocumentRecord:
        return _CODEC.serialize((await self.loaded()).document)

    async def gesture(self, *, intent_for: Callable[[VersionedDraftDocument], EditIntent]) -> None:
        loaded: VersionedDraftDocument = await self.loaded()
        intent: EditIntent = intent_for(loaded)
        with build_engine().transaction(document=loaded.document) as transaction:
            transaction.run(
                requests=build_compiler().compile(
                    document=loaded.document, intent=intent, entities=transaction.entities
                )
            )
        await self.history.commit(draft=loaded)

    async def stored(self) -> StoredDraft:
        stored: StoredDraft | None = await self.storage.get(draft_id=self.draft_id)
        assert stored is not None

        return stored


def _note_ids(*, loaded: VersionedDraftDocument, at: tuple[Fraction, ...]) -> list[str]:
    score: Score = Score(
        document=loaded.document,
        voice=loaded.document.voices[0],
        staff=loaded.document.staffs[0],
        measures=list(loaded.document.measures),
    )

    return [note_at(score=score, at=position).id for position in at]


def _tie(loaded: VersionedDraftDocument) -> EditIntent:
    start, end = _note_ids(loaded=loaded, at=(Fraction(0), Fraction(1, 4)))

    return TieNotesIntent(start_note_id=start, end_note_id=end)


def _delete_first(loaded: VersionedDraftDocument) -> EditIntent:
    (first,) = _note_ids(loaded=loaded, at=(Fraction(0),))

    return DeleteBatchIntent(entity_ids=(first,))


@pytest.mark.unit
async def test_a_tie_made_and_a_tied_note_deleted_are_taken_back_and_given_again_exactly() -> None:
    fixture: _Fixture = _Fixture()
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    await fixture.create(score=score)
    start: DocumentRecord = await fixture.record()

    await fixture.gesture(intent_for=_tie)
    tied: DocumentRecord = await fixture.record()
    await fixture.gesture(intent_for=_delete_first)
    deleted: DocumentRecord = await fixture.record()

    assert len(start["relation_ids"]) == 0
    assert len(tied["relation_ids"]) == 1
    assert deleted["relation_ids"] == []

    for expected in (tied, start):
        assert await fixture.history.undo(draft=await fixture.loaded())
        assert await fixture.record() == expected

    for expected in (tied, deleted):
        assert await fixture.history.redo(draft=await fixture.loaded())
        assert await fixture.record() == expected


@pytest.mark.unit
async def test_the_store_holds_the_ids_a_gesture_moved_and_not_the_whole_list() -> None:
    fixture: _Fixture = _Fixture()
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    await fixture.create(score=score)

    await fixture.gesture(intent_for=_tie)
    stored: StoredDraft = await fixture.stored()
    (change,) = stored.changes

    (relation_id,) = (await fixture.record())["relation_ids"]
    assert change["fields"]["relation_ids"] == {"removed": [], "inserted": [[0, relation_id]]}
    assert json.loads(json.dumps(change, sort_keys=True)) == change


@pytest.mark.unit
async def test_a_history_kept_for_many_gestures_walks_back_to_where_it_began() -> None:
    fixture: _Fixture = _Fixture()
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)
    await fixture.create(score=score)
    states: list[DocumentRecord] = [await fixture.record()]

    for gesture in (_tie, _delete_first):
        await fixture.gesture(intent_for=gesture)
        states.append(await fixture.record())

    for expected in reversed(states[:-1]):
        assert await fixture.history.undo(draft=await fixture.loaded())
        assert await fixture.record() == expected
    assert not await fixture.history.undo(draft=await fixture.loaded())
