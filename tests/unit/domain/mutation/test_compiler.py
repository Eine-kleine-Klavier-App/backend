from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation import build_compiler
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
from piano_app.domain.score.document.services.mutation.engine import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.analyzers.delete import (
    DeleteAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.intent import (
    RemoveAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.factory import (
    build_analyzer_registry,
    build_handler_registry,
    build_postprocessors,
)
from piano_app.domain.score.document.services.mutation.engine.guards import RelationGuard
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.registry import (
    MutationAnalyzerRegistry,
)
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
)

from ..scene import (
    Score,
    build_engine,
    build_score,
    check_geometry_after_action,
    check_geometry_at_checkpoint,
    delete_entities,
    eighth_triplet,
    insert_note,
    layout,
    note_at,
    quarters,
    rest,
    rest_at,
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


def _removals(*, score: Score, entity_ids: Sequence[str]) -> list[MutationWorkItem]:
    """The delete requests the batch's remove request yields, read off its analyzer with
    no engine: nothing executes, so nothing is skipped."""
    requests: Sequence[MutationRequest] = _compile_delete(score=score, entity_ids=entity_ids)
    assert len(requests) == 1
    remove: MutationRequest = requests[0]
    assert isinstance(remove, RemoveRequest)

    return list(
        RemoveAnalyzer().analyze(request=remove, geometry=ScoreGeometry(document=score.document))
    )


# --- the facade dispatches by intent type ---------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class _ProbeIntent(EditIntent):
    label: str


class _ProbeCompiler:
    def __init__(self) -> None:
        self.seen: list[_ProbeIntent] = []

    def compile(
        self, *, document: ScoreDocument, intent: _ProbeIntent, entities: EntityIndex
    ) -> Sequence[MutationRequest]:
        self.seen.append(intent)
        return []


@pytest.mark.unit
def test_the_facade_hands_an_intent_to_the_compiler_registered_for_its_type() -> None:
    score: Score = build_score(measure_count=1)
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
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(0)
    )
    leaf = triplet.children[2]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)
    deep: Note = leaf.carrier.notes[0]

    found: dict[str, ScoreEntity] = resolve_entities(
        entities=EntityIndex(document=score.document),
        entity_ids=[deep.id, triplet.id, score.voice.id],
    )

    assert found == {deep.id: deep, triplet.id: triplet, score.voice.id: score.voice}
    assert found[deep.id] is deep


@pytest.mark.unit
def test_resolution_refuses_naming_the_unknown_id() -> None:
    score: Score = build_score(measure_count=1)

    with pytest.raises(MutationRejectedError, match="ghost"):
        resolve_entities(
            entities=EntityIndex(document=score.document), entity_ids=[score.voice.id, "ghost"]
        )


@pytest.mark.unit
def test_an_entity_of_the_wrong_kind_is_refused_by_name() -> None:
    score: Score = build_score(measure_count=1)
    found: dict[str, ScoreEntity] = resolve_entities(
        entities=EntityIndex(document=score.document),
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
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=1)
    carriers: list[NoteCarrier] = _carriers(score=score)

    _tie(score=score, start=carriers[0].notes[0], end=carriers[1].notes[0])

    assert tie_pairs(score=score) == [(1, 1)]


@pytest.mark.unit
def test_notes_with_a_rest_between_them_are_not_tied() -> None:
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=score, at=Fraction(1, 2), rhythmic_value=RhythmicValue.QUARTER, step=2)
    carriers: list[NoteCarrier] = _carriers(score=score)

    with pytest.raises(MutationRejectedError, match="must touch"):
        _tie(score=score, start=carriers[0].notes[0], end=carriers[1].notes[0])

    assert tie_pairs(score=score) == []


@pytest.mark.unit
def test_a_tie_naming_a_carrier_instead_of_a_note_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
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
    score: Score = build_score(measure_count=1)

    with pytest.raises(MutationRejectedError, match="at least one"):
        _compile_delete(score=score, entity_ids=[])


@pytest.mark.unit
def test_a_delete_batch_naming_an_unsupported_entity_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    with pytest.raises(MutationRejectedError, match="Unsupported delete targets: Voice"):
        _compile_delete(score=score, entity_ids=[_carriers(score=score)[0].id, score.voice.id])


@pytest.mark.unit
def test_a_delete_batch_compiles_to_one_remove_request_over_the_listed_entities() -> None:
    """The compiler only addresses: what is held and in which order it goes is decided
    by the remove request's analyzer."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    note: Note = carriers[0].notes[0]

    requests = _compile_delete(score=score, entity_ids=[note.id, carriers[2].id, carriers[0].id])

    assert requests == [
        RemoveRequest(document=score.document, targets=(note, carriers[2], carriers[0]))
    ]


@pytest.mark.unit
def test_a_repeated_id_is_deleted_once() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    removals = _removals(score=score, entity_ids=[carrier.id, carrier.id])

    assert removals == [DeleteRequest(target=carrier)]


@pytest.mark.unit
def test_a_note_whose_carrier_is_also_deleted_is_left_to_the_carriers_cascade() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    removals = _removals(score=score, entity_ids=[carrier.notes[0].id, carrier.id])

    assert removals == [DeleteRequest(target=carrier)]


@pytest.mark.unit
def test_carriers_are_deleted_before_single_notes_whatever_the_order_of_ids() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    note: Note = carriers[0].notes[0]

    removals = _removals(score=score, entity_ids=[note.id, carriers[2].id, carriers[1].id])

    assert removals == [
        DeleteRequest(target=carriers[2]),
        DeleteRequest(target=carriers[1]),
        DeleteRequest(target=note),
    ]


@pytest.mark.unit
def test_the_remove_analyzer_skips_an_entity_already_removed_when_its_turn_comes() -> None:
    """Attachment is read on the live document before each yield, not when the set is
    reduced: a note removed after the first yield is passed over without a request."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    note: Note = carriers[0].notes[0]

    analysis: MutationAnalysis = RemoveAnalyzer().analyze(
        request=RemoveRequest(document=score.document, targets=(note, carriers[1])),
        geometry=ScoreGeometry(document=score.document),
    )
    first: MutationWorkItem = next(analysis)
    note.detach()

    assert first == DeleteRequest(target=carriers[1])
    assert list(analysis) == []


def _two_triplets_and_two_rests() -> Score:
    """Eighth triplets on beats one and two (staff steps 1, 2, 3), quarter rests on beats
    three and four."""
    score: Score = build_score(measure_count=1)
    eighth_triplet(score=score, parent=score.voice, at=Fraction(0))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    for beat in (2, 3):
        rest(
            score=score,
            parent=score.voice,
            at=Fraction(beat, 4),
            rhythmic_value=RhythmicValue.QUARTER,
        )

    return score


type _Removable = GroupRhythmicContainer | NoteCarrier | RestCarrier | Rest


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pick", "expected"),
    [
        pytest.param(
            lambda score: (score.voice.children[0], score.voice.children[1]),
            lambda target: DeleteRequest(target=target),
            id="a group",
        ),
        pytest.param(
            lambda score: (
                note_at(score=score, at=Fraction(0)).note_carrier,
                note_at(score=score, at=Fraction(1, 12)).note_carrier,
            ),
            lambda target: DeleteRequest(target=target),
            id="a note carrier",
        ),
        pytest.param(
            lambda score: (
                rest_at(score=score, at=Fraction(1, 2)).rest_carrier,
                rest_at(score=score, at=Fraction(3, 4)).rest_carrier,
            ),
            lambda target: DeleteRequest(target=target),
            id="a rest carrier",
        ),
        pytest.param(
            lambda score: (
                rest_at(score=score, at=Fraction(1, 2)),
                rest_at(score=score, at=Fraction(3, 4)),
            ),
            lambda target: DeleteRequest(target=target),
            id="a rest",
        ),
    ],
)
def test_the_remove_analyzer_skips_any_entity_already_removed_when_its_turn_comes(
    pick: Callable[[Score], tuple[_Removable, _Removable]],
    expected: Callable[[_Removable], MutationRequest],
) -> None:
    """The same live check at every level: the second entity of a kind, removed after the
    first one's request was yielded, is passed over without a request."""
    score: Score = _two_triplets_and_two_rests()
    first_target, second_target = pick(score)

    analysis: MutationAnalysis = RemoveAnalyzer().analyze(
        request=RemoveRequest(document=score.document, targets=(first_target, second_target)),
        geometry=ScoreGeometry(document=score.document),
    )
    first: MutationWorkItem = next(analysis)
    second_target.detach()

    assert first == expected(first_target)
    assert list(analysis) == []


class _DeleteSpy:
    """The real deletion, recording every entity it is asked to delete."""

    def __init__(self) -> None:
        self.expanded: list[ScoreEntity] = []

    def analyze(self, *, request: DeleteRequest, geometry: ScoreGeometry) -> MutationAnalysis:
        self.expanded.append(request.target)
        return DeleteAnalyzer().analyze(request=request, geometry=geometry)


@pytest.mark.unit
def test_an_entity_an_earlier_cascade_removed_is_skipped_without_an_error() -> None:
    """The first request of the gesture already takes the note with its carrier; the
    remove request never asks for it again and still removes the rest, as one gesture."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    note: Note = carriers[0].notes[0]
    before = layout(score=score)
    spy: _DeleteSpy = _DeleteSpy()
    analyzers: MutationAnalyzerRegistry = build_analyzer_registry()
    analyzers.register(request_type=DeleteRequest, analyzer=spy)
    engine: MutationEngine = MutationEngine(
        handler_registry=build_handler_registry(),
        analyzer_registry=analyzers,
        postprocessors=build_postprocessors(),
        guards=[RelationGuard()],
        geometry_check=check_geometry_after_action,
        checkpoint_geometry_check=check_geometry_at_checkpoint,
    )

    log: MutationLog = engine.process(
        document=score.document,
        requests=[
            DeleteRequest(target=carriers[0]),
            RemoveRequest(document=score.document, targets=(note, carriers[1])),
        ],
    )

    # once, by the carrier's own cascade; the remove request passes over it
    assert spy.expanded.count(note) == 1
    assert [entry.content for entry in layout(score=score)] == ["rest", "0", "0"]

    log.rollback()

    assert layout(score=score) == before


@pytest.mark.unit
def test_a_mixed_delete_batch_is_one_gesture_and_rolls_back_as_one() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(score=score)
    before = layout(score=score)

    log: MutationLog = delete_entities(
        score=score,
        entity_ids=[carriers[0].notes[0].id, carriers[3].id],
    )
    assert [entry.content for entry in layout(score=score)] == ["rest", "0", "0", "rest"]

    log.rollback()

    assert layout(score=score) == before
