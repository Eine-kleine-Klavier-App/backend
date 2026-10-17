from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    EditIntent,
    MutationCompiler,
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.registry import (
    IntentCompilerRegistry,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    DeleteNoteCarrierRequest,
    DeleteNoteRequest,
)

from ..scene import (
    Score,
    build_score,
    delete_entities,
    eighth_triplet,
    insert_note,
    layout,
    quarters,
    tie_pairs,
)

_Q: Fraction = Fraction(1, 4)


def _carriers(*, score: Score) -> list[NoteCarrier]:
    carriers: list[NoteCarrier] = []
    for child in score.voice.children:
        if isinstance(child, LeafRhythmicContainer) and isinstance(child.carrier, NoteCarrier):
            carriers.append(child.carrier)

    return carriers


def _compile_delete(*, score: Score, entity_ids: Sequence[str]) -> Sequence[MutationRequest]:
    return build_compiler().compile(
        document=score.document,
        intent=DeleteBatchIntent(entity_ids=tuple(entity_ids)),
    )


# --- the facade dispatches by intent type ---------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class _ProbeIntent(EditIntent):
    label: str


class _ProbeCompiler:
    def __init__(self) -> None:
        self.seen: list[_ProbeIntent] = []

    def compile(
        self, *, document: ScoreDocument, intent: _ProbeIntent
    ) -> Sequence[MutationRequest]:
        self.seen.append(intent)
        return []


@pytest.mark.unit
def test_the_facade_hands_an_intent_to_the_compiler_registered_for_its_type() -> None:
    score: Score = build_score(bars=1)
    probe: _ProbeCompiler = _ProbeCompiler()
    registry: IntentCompilerRegistry = IntentCompilerRegistry()
    registry.register(intent_type=_ProbeIntent, compiler=probe)
    intent: _ProbeIntent = _ProbeIntent(label="probe")

    requests = MutationCompiler(registry=registry).compile(document=score.document, intent=intent)

    assert requests == []
    assert probe.seen == [intent]


# --- id resolution ----------------------------------------------------------------------


@pytest.mark.unit
def test_resolution_reaches_entities_nested_deep_in_groups() -> None:
    score: Score = build_score(bars=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(0)
    )
    leaf = triplet.children[2]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)
    deep: Note = leaf.carrier.notes[0]

    found: dict[str, ScoreEntity] = resolve_entities(
        document=score.document,
        entity_ids=[deep.id, triplet.id, score.voice.id],
    )

    assert found == {deep.id: deep, triplet.id: triplet, score.voice.id: score.voice}
    assert found[deep.id] is deep


@pytest.mark.unit
def test_resolution_refuses_naming_the_unknown_id() -> None:
    score: Score = build_score(bars=1)

    with pytest.raises(MutationRejectedError, match="ghost"):
        resolve_entities(document=score.document, entity_ids=[score.voice.id, "ghost"])


@pytest.mark.unit
def test_an_entity_of_the_wrong_kind_is_refused_by_name() -> None:
    score: Score = build_score(bars=1)
    found: dict[str, ScoreEntity] = resolve_entities(
        document=score.document,
        entity_ids=[score.voice.id],
    )

    with pytest.raises(MutationRejectedError, match="must be Note, got Voice"):
        expect_entity(entities_by_id=found, entity_id=score.voice.id, expected=Note)


# --- tie notes --------------------------------------------------------------------------


def _tie(*, score: Score, start: Note, end: Note) -> MutationLog:
    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(
            document=score.document,
            intent=TieNotesIntent(start_note_id=start.id, end_note_id=end.id),
        ),
    )


@pytest.mark.unit
def test_two_adjacent_notes_are_tied() -> None:
    score: Score = build_score(bars=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=2)
    carriers: list[NoteCarrier] = _carriers(score=score)

    _tie(score=score, start=carriers[0].notes[0], end=carriers[1].notes[0])

    assert tie_pairs(score=score) == [(1, 2)]


@pytest.mark.unit
def test_notes_with_a_rest_between_them_are_not_tied() -> None:
    score: Score = build_score(bars=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=score, at=Fraction(1, 2), rhythmic_value=RhythmicValue.QUARTER, step=2)
    carriers: list[NoteCarrier] = _carriers(score=score)

    with pytest.raises(MutationRejectedError, match="adjacent"):
        _tie(score=score, start=carriers[0].notes[0], end=carriers[1].notes[0])

    assert tie_pairs(score=score) == []


@pytest.mark.unit
def test_a_tie_naming_a_carrier_instead_of_a_note_is_refused() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carriers: list[NoteCarrier] = _carriers(score=score)

    with pytest.raises(MutationRejectedError, match="must be Note"):
        build_compiler().compile(
            document=score.document,
            intent=TieNotesIntent(
                start_note_id=carriers[0].id, end_note_id=carriers[1].notes[0].id
            ),
        )


# --- delete batch -----------------------------------------------------------------------


@pytest.mark.unit
def test_an_empty_delete_batch_is_refused() -> None:
    score: Score = build_score(bars=1)

    with pytest.raises(MutationRejectedError, match="at least one"):
        _compile_delete(score=score, entity_ids=[])


@pytest.mark.unit
def test_a_delete_batch_naming_an_unsupported_entity_is_refused() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)

    with pytest.raises(MutationRejectedError, match="Unsupported delete targets: Voice"):
        _compile_delete(score=score, entity_ids=[_carriers(score=score)[0].id, score.voice.id])


@pytest.mark.unit
def test_a_repeated_id_is_deleted_once() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    requests = _compile_delete(score=score, entity_ids=[carrier.id, carrier.id])

    assert requests == [DeleteNoteCarrierRequest(target=carrier)]


@pytest.mark.unit
def test_a_note_whose_carrier_is_also_deleted_is_left_to_the_carriers_cascade() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    requests = _compile_delete(score=score, entity_ids=[carrier.notes[0].id, carrier.id])

    assert requests == [DeleteNoteCarrierRequest(target=carrier)]


@pytest.mark.unit
def test_carriers_are_deleted_before_single_notes_whatever_the_order_of_ids() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    note: Note = carriers[0].notes[0]

    requests = _compile_delete(score=score, entity_ids=[note.id, carriers[2].id, carriers[1].id])

    assert requests == [
        DeleteNoteCarrierRequest(target=carriers[2]),
        DeleteNoteCarrierRequest(target=carriers[1]),
        DeleteNoteRequest(target=note),
    ]


@pytest.mark.unit
def test_a_mixed_delete_batch_is_one_gesture_and_rolls_back_as_one() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    before = layout(score=score)

    log: MutationLog = delete_entities(
        score=score,
        entity_ids=[carriers[0].notes[0].id, carriers[3].id],
    )
    assert [entry.content for entry in layout(score=score)] == ["rest", "0", "0", "rest"]

    log.rollback()

    assert layout(score=score) == before
