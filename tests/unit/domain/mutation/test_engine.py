from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import cast

import pytest

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    Clef,
    Fingering,
    GlissandoType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando, Tie
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
from piano_app.domain.score.document.services.mutation.engine.analyzers.delete import (
    DeleteAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.material import (
    CreateNoteAnalyzer,
    CreateNoteCarrierAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    CreateLeafAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.temporal import (
    CreateTemporalAnchorAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.factory import (
    build_analyzer_registry,
    build_handler_registry,
)
from piano_app.domain.score.document.services.mutation.engine.guards import InvariantGuard
from piano_app.domain.score.document.services.mutation.engine.handlers import MutationHandler
from piano_app.domain.score.document.services.mutation.engine.handlers.material import (
    CreateNoteCarrierHandler,
    CreateNoteHandler,
    UpdateArticulationHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.rhythmic import (
    CreateLeafHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.temporal import (
    CreateTemporalAnchorHandler,
    DeleteTemporalAnchorHandler,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    EmptyGroupsPostprocessor,
    EmptyLeavesPostprocessor,
    MutatedStatePostprocessor,
    OrphanAnchorsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.engine.registry import (
    MutationAnalyzerRegistry,
    MutationHandlerRegistry,
)
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationAction,
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteAction,
    CreateNoteCarrierAction,
    UpdateArticulationAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateLeafAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    DeleteTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateNoteRequest,
    UpdateArticulationRequest,
    UpdateFingeringRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateLeafRequest,
    CreateRhythmicGroupRequest,
    NoteContent,
    PlaceSpansRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
    UpdateTemporalAnchorRequest,
)

from ..scene import (
    NEW_STEP,
    Score,
    anchor_at,
    broken_relations,
    build_engine,
    build_score,
    check_geometry_after_action,
    check_geometry_at_checkpoint,
    eighth_triplet,
    group,
    layout,
    note,
    note_at,
    orphan_anchors,
    quarters,
    rest,
    size,
    slot,
    value,
)

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)


def _create_note(
    *,
    score: Score,
    at: Fraction,
    rhythmic_value: RhythmicValue,
) -> MutationLog:
    """A note's request sent straight to the engine: its spans are placed in the deepest
    scope holding its start, and what they meet goes."""
    measure: Measure = score.measures[int(at)]
    position: MeasurePosition = MeasurePosition.of_fraction(fraction=at - int(at))
    written_length: Fraction = value(rhythmic_value).fraction

    return build_engine().process(
        document=score.document,
        requests=[
            PlaceSpansRequest(
                voice=score.voice,
                measure=measure,
                position=position,
                written_length=written_length,
                content=NoteContent(
                    staff=score.staff,
                    staff_step=NEW_STEP,
                    accidental=Accidental.NATURAL,
                ),
            ),
        ],
    )


def _process(*, score: Score, requests: list[MutationRequest]) -> MutationLog:
    return build_engine().process(document=score.document, requests=requests)


# --- the engine drives generator analyzers and guards their own terminal --------------


class _ScriptedAnalyzer[R: MutationRequest]:
    """A generator analyzer whose body the test writes."""

    def __init__(self, *, script: Callable[[R], MutationAnalysis]) -> None:
        self._script: Callable[[R], MutationAnalysis] = script

    def analyze(
        self,
        *,
        request: R,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        return self._script(request)


def _create_chain_analyzers() -> MutationAnalyzerRegistry:
    """The real note create chain and anchor deletion; a test replaces the analyzer it
    scripts."""
    registry: MutationAnalyzerRegistry = MutationAnalyzerRegistry()
    registry.register(request_type=CreateNoteRequest, analyzer=CreateNoteAnalyzer())
    registry.register(request_type=CreateNoteCarrierRequest, analyzer=CreateNoteCarrierAnalyzer())
    registry.register(request_type=CreateLeafRequest, analyzer=CreateLeafAnalyzer())
    registry.register(
        request_type=CreateTemporalAnchorRequest,
        analyzer=CreateTemporalAnchorAnalyzer(),
    )
    registry.register(
        request_type=DeleteRequest,
        analyzer=DeleteAnalyzer(),
    )

    return registry


def _engine(*, analyzer_registry: MutationAnalyzerRegistry) -> MutationEngine:
    """An engine without postprocessors or guards, so a run shows only what the analyzers
    yield."""
    handler_registry: MutationHandlerRegistry = MutationHandlerRegistry()
    handler_registry.register(action_type=CreateNoteAction, handler=CreateNoteHandler())
    handler_registry.register(
        action_type=CreateNoteCarrierAction,
        handler=CreateNoteCarrierHandler(),
    )
    handler_registry.register(action_type=CreateLeafAction, handler=CreateLeafHandler())
    handler_registry.register(
        action_type=CreateTemporalAnchorAction,
        handler=CreateTemporalAnchorHandler(),
    )
    handler_registry.register(
        action_type=DeleteTemporalAnchorAction,
        handler=DeleteTemporalAnchorHandler(),
    )

    # the scripted analyzers do not tell the geometry what they change, so it is not compared
    return MutationEngine(
        handler_registry=handler_registry,
        analyzer_registry=analyzer_registry,
        postprocessors=[],
        guards=[],
    )


def _anchor_request(*, score: Score) -> CreateTemporalAnchorRequest:
    return CreateTemporalAnchorRequest(
        measure=score.measures[0],
        position=MeasurePosition.of(numerator=0, denominator=1),
    )


def _leaf_request(*, score: Score) -> CreateLeafRequest:
    return CreateLeafRequest(
        scope=score.voice,
        measure=score.measures[0],
        position=MeasurePosition.of(numerator=0, denominator=1),
        written_size=size(RhythmicValue.QUARTER),
    )


@pytest.mark.unit
def test_an_analyzer_resumes_with_what_it_yielded_and_sees_it_in_the_live_document() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    seen: list[ScoreEntity | None] = []

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        anchor: ScoreEntity | None = yield CreateTemporalAnchorRequest(
            measure=request.measure,
            position=request.position,
        )
        assert isinstance(anchor, TemporalAnchor)
        seen.append(anchor)
        seen.append(find_anchor_at(measure=request.measure, position=request.position))

        leaf: ScoreEntity | None = yield CreateLeafAction(
            parent=score.voice,
            anchor=anchor,
            size=request.written_size,
        )
        seen.append(leaf)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[_leaf_request(score=score)],
    )

    leaf = score.voice.children[0]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert seen == [leaf.anchor, leaf.anchor, leaf]


@pytest.mark.unit
def test_a_yielded_request_sends_back_its_own_terminal_entity_and_a_delete_sends_none() -> None:
    """The leaf creates an anchor on the way; each analyzer that yielded a leaf, a carrier
    and a note gets exactly that entity back."""
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    seen: list[ScoreEntity | None] = []

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        leaf: ScoreEntity | None = yield CreateLeafRequest(
            scope=score.voice,
            measure=score.measures[0],
            position=MeasurePosition.of_fraction(fraction=_Q),
            written_size=size(RhythmicValue.QUARTER),
        )
        assert isinstance(leaf, LeafRhythmicContainer)
        seen.append(leaf)
        carrier: ScoreEntity | None = yield CreateNoteCarrierRequest(owner=leaf)
        assert isinstance(carrier, NoteCarrier)
        seen.append(carrier)
        seen.append(
            (
                yield CreateNoteRequest(
                    carrier=carrier,
                    staff=score.staff,
                    staff_step=NEW_STEP,
                    accidental=Accidental.NATURAL,
                )
            )
        )
        seen.append((yield DeleteTemporalAnchorAction(target=request.target)))

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[DeleteRequest(target=anchor)],
    )

    created: Note = note_at(score=score, at=_Q)
    assert seen == [created.note_carrier.owner, created.note_carrier, created, None]
    assert anchor not in score.measures[0].anchors


@pytest.mark.unit
def test_a_request_resolves_to_its_terminal_even_when_items_follow_it() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    seen: list[ScoreEntity | None] = []

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        anchor: ScoreEntity | None = yield CreateTemporalAnchorRequest(
            measure=request.measure,
            position=request.position,
        )
        assert isinstance(anchor, TemporalAnchor)
        yield CreateLeafAction(parent=score.voice, anchor=anchor, size=request.written_size)
        yield CreateTemporalAnchorRequest(
            measure=request.measure,
            position=MeasurePosition.of_fraction(fraction=Fraction(1, 2)),
        )

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        seen.append((yield _leaf_request(score=score)))
        yield DeleteTemporalAnchorAction(target=request.target)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[DeleteRequest(target=anchor_at(score=score, at=Fraction(3, 4)))],
    )

    assert seen == [score.voice.children[0]]
    assert len(score.measures[0].anchors) == 2


@pytest.mark.unit
def test_the_engine_refuses_an_action_of_another_kind() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    anchor: TemporalAnchor = anchor_at(score=score, at=_Q)

    def create_anchor(request: CreateTemporalAnchorRequest) -> MutationAnalysis:
        yield DeleteTemporalAnchorAction(target=anchor)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateTemporalAnchorRequest,
        analyzer=_ScriptedAnalyzer(script=create_anchor),
    )

    with pytest.raises(ValueError, match="kind"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[_anchor_request(score=score)],
        )

    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_the_engine_refuses_a_delete_action_targeting_another_entity() -> None:
    score: Score = build_score(measure_count=1)
    first: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    second: TemporalAnchor = anchor_at(score=score, at=_Q)

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        yield DeleteTemporalAnchorAction(target=second)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    with pytest.raises(ValueError, match="target mismatch"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[DeleteRequest(target=first)],
        )

    assert score.measures[0].anchors == [first, second]


@pytest.mark.unit
def test_the_engine_refuses_a_second_action_and_rolls_back_the_first() -> None:
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        yield DeleteTemporalAnchorAction(target=request.target)
        yield DeleteTemporalAnchorAction(target=request.target)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    with pytest.raises(ValueError, match="only one action"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[DeleteRequest(target=anchor)],
        )

    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_a_create_request_ending_without_its_terminal_is_refused_and_rolled_back() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    anchor: TemporalAnchor = anchor_at(score=score, at=_Q)

    def create_anchor(request: CreateTemporalAnchorRequest) -> MutationAnalysis:
        yield DeleteRequest(target=anchor)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateTemporalAnchorRequest,
        analyzer=_ScriptedAnalyzer(script=create_anchor),
    )

    with pytest.raises(ValueError, match="without its terminal"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[_anchor_request(score=score)],
        )

    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_a_delete_request_may_end_without_a_terminal() -> None:
    """Only a create promises an entity to its consumers."""
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        yield from ()

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[DeleteRequest(target=anchor)],
    )

    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_the_engine_refuses_an_update_action_targeting_another_entity() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    first: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    second: NoteCarrier = note_at(score=score, at=_Q).note_carrier

    def update_stem(request: UpdateArticulationRequest) -> MutationAnalysis:
        yield UpdateArticulationAction(target=second, articulations=request.articulations)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=UpdateArticulationRequest,
        analyzer=_ScriptedAnalyzer(script=update_stem),
    )

    with pytest.raises(
        ValueError,
        match=r"UpdateArticulationRequest yielded UpdateArticulationAction.*target mismatch",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[
                UpdateArticulationRequest(
                    target=first, articulations=frozenset({Articulation.ACCENT})
                )
            ],
        )


@pytest.mark.unit
def test_the_engine_refuses_an_item_that_is_neither_a_request_nor_an_action() -> None:
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        # mistyped on purpose: the engine checks what an analyzer really yields
        yield cast(MutationWorkItem, request.target)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    with pytest.raises(TypeError, match="DeleteRequest yielded TemporalAnchor"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[DeleteRequest(target=anchor)],
        )


@pytest.mark.unit
def test_a_failing_sub_request_closes_the_analyzer_before_the_gesture_rolls_back() -> None:
    """The anchor the first sub-request created is still there when the analyzer's cleanup
    runs, and gone once the gesture has rolled back."""
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    anchors_at_close: list[int] = []

    def delete_anchor(request: DeleteRequest) -> MutationAnalysis:
        try:
            yield CreateTemporalAnchorRequest(
                measure=score.measures[0],
                position=MeasurePosition.of_fraction(fraction=_Q),
            )
            # an anchor past the end of its measure is refused by its analyzer
            yield CreateTemporalAnchorRequest(
                measure=score.measures[0],
                position=MeasurePosition.of_fraction(fraction=Fraction(5, 4)),
            )
            yield DeleteTemporalAnchorAction(target=request.target)
        finally:
            anchors_at_close.append(len(score.measures[0].anchors))

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=DeleteRequest,
        analyzer=_ScriptedAnalyzer(script=delete_anchor),
    )

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[DeleteRequest(target=anchor)],
        )

    assert anchors_at_close == [2]
    assert score.measures[0].anchors == [anchor]


class _ScriptedHandler[A: MutationAction]:
    """A handler whose body the test writes."""

    def __init__(self, *, script: Callable[[A, MutationSink], ScoreEntity | None]) -> None:
        self._script: Callable[[A, MutationSink], ScoreEntity | None] = script

    def handle(self, *, action: A, sink: MutationSink) -> ScoreEntity | None:
        return self._script(action, sink)


def _engine_with_handler[A: MutationAction](
    *,
    action_type: type[A],
    handler: MutationHandler[A],
) -> MutationEngine:
    """The real analyzers and handlers with one handler replaced, and no postprocessors or
    guards."""
    handler_registry: MutationHandlerRegistry = build_handler_registry()
    handler_registry.register(action_type=action_type, handler=handler)

    return MutationEngine(
        handler_registry=handler_registry,
        analyzer_registry=build_analyzer_registry(),
        postprocessors=[],
        guards=[],
        geometry_check=check_geometry_after_action,
        checkpoint_geometry_check=check_geometry_at_checkpoint,
    )


@pytest.mark.unit
def test_a_create_handler_producing_nothing_is_refused() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)

    def create_anchor(action: CreateTemporalAnchorAction, sink: MutationSink) -> ScoreEntity | None:
        return None

    engine: MutationEngine = _engine_with_handler(
        action_type=CreateTemporalAnchorAction,
        handler=_ScriptedHandler(script=create_anchor),
    )

    with pytest.raises(
        ValueError, match="Create handler produced nothing: CreateTemporalAnchorAction"
    ):
        engine.process(document=score.document, requests=[_anchor_request(score=score)])

    assert score.measures[0].anchors == []


@pytest.mark.unit
def test_a_delete_handler_producing_an_entity_is_refused_and_its_deletion_rolled_back() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    anchor: TemporalAnchor = anchor_at(score=score, at=_Q)

    def delete_anchor(action: DeleteTemporalAnchorAction, sink: MutationSink) -> ScoreEntity | None:
        DeleteTemporalAnchorHandler().handle(action=action, sink=sink)
        return action.target

    engine: MutationEngine = _engine_with_handler(
        action_type=DeleteTemporalAnchorAction,
        handler=_ScriptedHandler(script=delete_anchor),
    )

    with pytest.raises(
        ValueError, match="Delete handler produced an entity: DeleteTemporalAnchorAction"
    ):
        engine.process(document=score.document, requests=[DeleteRequest(target=anchor)])

    assert score.measures[0].anchors == [anchor]


@pytest.mark.unit
def test_an_update_handler_producing_an_entity_is_refused_and_its_update_rolled_back() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier

    def update_stem(action: UpdateArticulationAction, sink: MutationSink) -> ScoreEntity | None:
        UpdateArticulationHandler().handle(action=action, sink=sink)
        return action.target

    engine: MutationEngine = _engine_with_handler(
        action_type=UpdateArticulationAction,
        handler=_ScriptedHandler(script=update_stem),
    )

    with pytest.raises(
        ValueError, match="Update handler produced an entity: UpdateArticulationAction"
    ):
        engine.process(
            document=score.document,
            requests=[
                UpdateArticulationRequest(
                    target=carrier, articulations=frozenset({Articulation.ACCENT})
                )
            ],
        )

    assert not carrier.articulations


@pytest.mark.unit
def test_an_analyzer_narrowing_what_was_sent_back_refuses_anything_else() -> None:
    """``expect_sent`` is where an analyzer receives a yielded create's entity: what its
    request does not create, or nothing, is a broken engine contract."""
    score: Score = build_score(measure_count=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    assert expect_sent(sent=anchor, expected=TemporalAnchor) is anchor

    with pytest.raises(TypeError, match="Expected Note to be sent back, got TemporalAnchor"):
        expect_sent(sent=anchor, expected=Note)

    with pytest.raises(TypeError, match="Expected Note to be sent back, got nothing"):
        expect_sent(sent=None, expected=Note)


# --- the axis contract and what a request sends back ----------------------------------


def _yield_nothing(request: MutationRequest) -> MutationAnalysis:
    """A no-op analyzer body: legitimate for a delete, which promises no entity."""
    yield from ()


@pytest.mark.unit
def test_every_registered_request_type_declares_its_tags_in_its_own_body() -> None:
    """The bases leave ``axis`` and, for a create, ``creates`` unset, so a request type that
    forgets one would fail only when the engine checks it; an inherited tag would pass
    silently."""
    request_types: list[type[MutationRequest]] = [
        *build_analyzer_registry()._analyzers,
        *build_analyzer_registry()._pitch_analyzers,
    ]

    untagged: list[str] = [
        request_type.__name__ for request_type in request_types if "axis" not in vars(request_type)
    ]
    assert untagged == []

    uncreating: list[str] = [
        request_type.__name__
        for request_type in request_types
        if issubclass(request_type, CreateMutationRequest) and "creates" not in vars(request_type)
    ]
    assert uncreating == []

    exempt: set[type[MutationRequest]] = {
        request_type for request_type in request_types if request_type.axis is None
    }
    assert exempt == {
        CreateTemporalAnchorRequest,
        DeleteRequest,
        UpdateTemporalAnchorRequest,
    }


@pytest.mark.unit
def test_a_native_analyzer_yielding_a_request_of_a_higher_axis_is_refused() -> None:
    """Refused before the yielded request is expanded: its analyzer never runs."""
    score: Score = build_score(measure_count=1, start_contexts=False)
    quarters(score=score, measure=0, beats=(1,))
    target: Note = note_at(score=score, at=_Q)
    expanded: list[CreateLeafRequest] = []

    def update_fingering(request: UpdateFingeringRequest) -> MutationAnalysis:
        yield _leaf_request(score=score)

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        expanded.append(request)
        yield from ()

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=UpdateFingeringRequest, analyzer=_ScriptedAnalyzer(script=update_fingering)
    )
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )

    with pytest.raises(
        ValueError,
        match=r"UpdateFingeringRequest \(CONTENT\) yielded CreateLeafRequest \(SPANS\), whose axis",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[UpdateFingeringRequest(target=target, fingering=Fingering.NONE)],
        )

    assert expanded == []
    assert len(score.voice.children) == 1
    assert len(score.measures[0].anchors) == 1


@pytest.mark.unit
def test_a_native_analyzer_may_yield_requests_of_its_own_and_of_a_lower_axis() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    met: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=_Q,
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    seen: list[ScoreEntity | None] = []

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        seen.append((yield DeleteRequest(target=met)))
        seen.append((yield DeleteRequest(target=note_at(score=score, at=_Q))))
        anchor: ScoreEntity | None = yield CreateTemporalAnchorRequest(
            measure=request.measure,
            position=request.position,
        )
        assert isinstance(anchor, TemporalAnchor)
        seen.append(
            (yield CreateLeafAction(parent=score.voice, anchor=anchor, size=request.written_size))
        )

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )
    analyzers.register(
        request_type=DeleteRequest, analyzer=_ScriptedAnalyzer(script=_yield_nothing)
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[_leaf_request(score=score)],
    )

    created: ScoreEntity | None = seen[-1]
    assert isinstance(created, LeafRhythmicContainer)
    assert created.anchor.position.value == Fraction(0)
    assert seen == [None, None, created]


@pytest.mark.unit
def test_a_native_rhythm_analyzer_may_not_yield_a_context_request() -> None:
    """Contexts share no rank with rhythm: even relations, the lowest rhythm axis, may not
    reach them."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))

    def create_tie(request: CreateTieRequest) -> MutationAnalysis:
        yield CreateClefChangeRequest(
            measure=score.measures[0],
            position=MeasurePosition.of_fraction(fraction=Fraction(0)),
            staff=score.staff,
            clef=Clef.BASS,
        )

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(request_type=CreateTieRequest, analyzer=_ScriptedAnalyzer(script=create_tie))

    with pytest.raises(
        ValueError,
        match=r"CreateTieRequest \(RELATIONS\) yielded CreateClefChangeRequest \(CONTEXTS\), "
        "across contexts and rhythm",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[
                CreateTieRequest(
                    start_note=note_at(score=score, at=Fraction(0)),
                    end_note=note_at(score=score, at=_Q),
                )
            ],
        )


@pytest.mark.unit
def test_a_native_context_analyzer_may_not_yield_a_rhythm_request() -> None:
    score: Score = build_score(measure_count=1)

    def create_clef(request: CreateClefChangeRequest) -> MutationAnalysis:
        yield _leaf_request(score=score)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateClefChangeRequest, analyzer=_ScriptedAnalyzer(script=create_clef)
    )

    with pytest.raises(
        ValueError,
        match=r"CreateClefChangeRequest \(CONTEXTS\) yielded CreateLeafRequest \(SPANS\), "
        "across contexts and rhythm",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[
                CreateClefChangeRequest(
                    measure=score.measures[0],
                    position=MeasurePosition.of_fraction(fraction=Fraction(0)),
                    staff=score.staff,
                    clef=Clef.BASS,
                )
            ],
        )

    assert score.voice.children == []


@pytest.mark.unit
def test_an_anchor_request_may_be_yielded_from_any_axis() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))

    def update_fingering(request: UpdateFingeringRequest) -> MutationAnalysis:
        yield CreateTemporalAnchorRequest(
            measure=score.measures[0],
            position=MeasurePosition.of_fraction(fraction=_Q),
        )

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=UpdateFingeringRequest, analyzer=_ScriptedAnalyzer(script=update_fingering)
    )

    _engine(analyzer_registry=analyzers).process(
        document=score.document,
        requests=[
            UpdateFingeringRequest(
                target=note_at(score=score, at=Fraction(0)), fingering=Fingering.NONE
            )
        ],
    )

    assert find_anchor_at(
        measure=score.measures[0], position=MeasurePosition.of_fraction(fraction=_Q)
    )


@pytest.mark.unit
def test_an_anchor_request_inherits_its_ancestors_axis_and_opens_no_upward_path() -> None:
    """Content → deletion → group creation: the deletion is held to the content axis it was
    yielded from, so the frames request is refused before it runs."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    expanded: list[CreateRhythmicGroupRequest] = []

    def update_fingering(request: UpdateFingeringRequest) -> MutationAnalysis:
        yield DeleteRequest(target=anchor)

    def delete(request: DeleteRequest) -> MutationAnalysis:
        yield CreateRhythmicGroupRequest(
            voice=score.voice,
            measure=score.measures[0],
            position=MeasurePosition.of_fraction(fraction=_Q),
            written_size=size(RhythmicValue.QUARTER),
            occupied_size=size(RhythmicValue.QUARTER),
        )

    def create_group(request: CreateRhythmicGroupRequest) -> MutationAnalysis:
        expanded.append(request)
        yield from ()

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=UpdateFingeringRequest, analyzer=_ScriptedAnalyzer(script=update_fingering)
    )
    analyzers.register(request_type=DeleteRequest, analyzer=_ScriptedAnalyzer(script=delete))
    analyzers.register(
        request_type=CreateRhythmicGroupRequest, analyzer=_ScriptedAnalyzer(script=create_group)
    )

    with pytest.raises(
        ValueError,
        match=r"DeleteRequest \(CONTENT, inherited\) yielded "
        r"CreateRhythmicGroupRequest \(FRAMES\), whose axis ranks higher",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[
                UpdateFingeringRequest(
                    target=note_at(score=score, at=Fraction(0)), fingering=Fingering.NONE
                )
            ],
        )

    assert expanded == []


@pytest.mark.unit
def test_a_create_yielding_a_create_action_of_another_entity_type_is_refused() -> None:
    """A create action is its request's terminal only when it creates what the request
    ``creates``: an anchor is not the leaf a leaf request sends back."""
    score: Score = build_score(measure_count=1, start_contexts=False)

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        yield CreateTemporalAnchorAction(measure=request.measure, position=request.position)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )

    with pytest.raises(
        ValueError,
        match="CreateLeafRequest sends back TemporalAnchor, not the LeafRhythmicContainer",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[_leaf_request(score=score)],
        )

    assert score.measures[0].anchors == []


def _place_spans_request(*, score: Score) -> MutationRequest:
    return PlaceSpansRequest(
        voice=score.voice,
        measure=score.measures[0],
        position=MeasurePosition.of_fraction(fraction=Fraction(0)),
        written_length=_Q,
        content=NoteContent(staff=score.staff, staff_step=NEW_STEP, accidental=Accidental.NATURAL),
    )


def _remove_request(*, score: Score) -> MutationRequest:
    return RemoveRequest(document=score.document, targets=(note_at(score=score, at=Fraction(0)),))


@pytest.mark.unit
@pytest.mark.parametrize(
    "build_request",
    [_place_spans_request, _remove_request],
    ids=["place spans", "remove"],
)
def test_a_request_without_a_terminal_may_not_yield_an_action(
    build_request: Callable[..., MutationRequest],
) -> None:
    """Placing and removing only yield requests: any action they yielded would bypass the
    analyzer of the entity it touches."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    request: MutationRequest = build_request(score=score)

    def yield_action(request: MutationRequest) -> MutationAnalysis:
        yield DeleteTemporalAnchorAction(target=anchor)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(request_type=type(request), analyzer=_ScriptedAnalyzer(script=yield_action))

    with pytest.raises(
        ValueError,
        match=f"{type(request).__name__} yielded DeleteTemporalAnchorAction, whose kind",
    ):
        _engine(analyzer_registry=analyzers).process(
            document=score.document,
            requests=[request],
        )

    assert anchor in score.measures[0].anchors


# --- the create chain with an explicit scope ----------------------------------------


@pytest.mark.unit
def test_a_note_in_an_empty_voice_builds_the_whole_chain_and_the_measure_is_tiled() -> None:
    score: Score = build_score(measure_count=2)

    _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _Q, str(NEW_STEP)),
        slot(0, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]
    # the second measure is never reached, so it stays asleep
    assert score.measures[1].anchors == []


@pytest.mark.unit
def test_a_note_goes_into_the_deepest_group_holding_its_start() -> None:
    """The scope is found on the live document — a start on a group's first instant is
    inside it — and the rest of the group's room is filled in the group's units."""
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH)

    owner = note_at(score=score, at=Fraction(0)).note_carrier.owner
    assert isinstance(owner, LeafRhythmicContainer)
    assert owner.parent is triplet
    assert layout(score=score) == [
        slot(0, Fraction(0), _E, str(NEW_STEP), depth=1),
        slot(0, Fraction(1, 12), _Q, "rest", depth=1),
        slot(0, _Q, Fraction(3, 4), "rest"),
    ]


@pytest.mark.unit
def test_a_note_on_a_same_size_note_joins_it_as_a_chord() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert [entry.content for entry in layout(score=score)] == ["0", f"0,{NEW_STEP}", "0", "0"]


@pytest.mark.unit
def test_an_item_at_a_groups_first_instant_running_past_its_end_is_refused() -> None:
    """A start on a group's first instant lies inside the group, so a half there must fit
    the triplet's three written eighths — it does not, and nothing changes."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))
    before = layout(score=score)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == before


@pytest.mark.unit
def test_a_group_hit_at_voice_level_is_displaced_whole() -> None:
    """A half from beat one meets the quarter and the triplet after it: both go, the
    triplet with every inner note, and nothing is left on the triplet's anchors."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))

    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []
    assert [anchor.position.value for anchor in score.measures[0].anchors] == [
        Fraction(0),
        Fraction(1, 2),
        Fraction(3, 4),
    ]


@pytest.mark.unit
def test_a_second_leaf_at_one_slot_replaces_the_first_rather_than_joining_it() -> None:
    """At most one container per scope starts at an anchor: a different size at an
    occupied slot displaces what was there."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    anchor: TemporalAnchor = score.measures[0].anchors[0]
    assert [container.parent for container in anchor.containers] == [score.voice]
    assert layout(score=score)[0] == slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP))


@pytest.mark.unit
def test_a_leaf_whose_room_is_not_clear_is_a_broken_invariant() -> None:
    """The leaf displaces nothing: whoever places spans clears the room first."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before = layout(score=score)

    anchors: list[TemporalAnchor] = list(score.measures[0].anchors)

    with pytest.raises(ValueError, match=r"would meet 1 container\(s\) of its scope"):
        _process(score=score, requests=[_leaf_request(score=score)])

    assert layout(score=score) == before
    assert score.measures[0].anchors == anchors


# --- deletion cascade -----------------------------------------------------------------


@pytest.mark.unit
def test_deleting_a_group_deletes_every_container_inside_it_at_every_depth() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 2, 3))
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=_Q + Fraction(index, 36),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=1,
        )
    for index in (1, 2):
        note(
            score=score,
            parent=outer,
            at=_Q + Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=2,
        )

    _process(score=score, requests=[DeleteRequest(target=outer)])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []
    assert len(score.measures[0].anchors) == 4


@pytest.mark.unit
def test_deleting_an_anchor_shared_by_nested_containers_deletes_each_once() -> None:
    """Outer group, inner group and leaf all start here; only the outermost is deleted
    by the anchor — the rest goes with it, never twice."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(1),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    note(score=score, parent=inner, at=Fraction(1), rhythmic_value=RhythmicValue.SIXTEENTH, step=1)
    quarters(score=score, measure=1, beats=(1, 2, 3))
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(1))

    _process(score=score, requests=[DeleteRequest(target=anchor)])

    assert anchor not in score.measures[1].anchors
    assert layout(score=score)[4] == slot(1, Fraction(0), _Q, "rest")
    assert not any(entry.depth for entry in layout(score=score))


@pytest.mark.unit
def test_deleting_an_anchor_deletes_the_leaf_starting_there_and_the_fill_rests_its_room() -> None:
    """The leaf goes with its note before the anchor; the fill then places a rest in the
    hole, at an anchor of its own."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    anchor: TemporalAnchor = anchor_at(score=score, at=_Q)
    gone: Note = note_at(score=score, at=_Q)

    _process(score=score, requests=[DeleteRequest(target=anchor)])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert anchor not in score.measures[0].anchors
    assert gone not in score.staff.musical_items
    assert len(score.measures[0].anchors) == 4
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_a_note_of_a_chord_keeps_the_carrier() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    carrier = score.voice.children[0]
    assert isinstance(carrier, LeafRhythmicContainer)
    assert isinstance(carrier.carrier, NoteCarrier)
    added: Note = carrier.carrier.notes[-1]

    _process(score=score, requests=[DeleteRequest(target=added)])

    assert [entry.content for entry in layout(score=score)] == ["0", "0", "0", "0"]


@pytest.mark.unit
def test_deleting_the_only_note_unwinds_carrier_leaf_and_refills_with_a_rest() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    _process(score=score, requests=[DeleteRequest(target=leaf.carrier.notes[0])])

    assert [entry.content for entry in layout(score=score)] == ["0", "rest", "0", "0"]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_a_carrier_cascades_down_to_its_notes() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    leaf = score.voice.children[3]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)
    gone: Note = leaf.carrier.notes[0]

    _process(score=score, requests=[DeleteRequest(target=leaf.carrier)])

    assert gone not in score.staff.musical_items
    assert [entry.content for entry in layout(score=score)] == ["0", "0", "0", "rest"]


# --- the posts: what each one reports ------------------------------------------------


@pytest.mark.unit
def test_the_empty_leaves_post_reports_every_leaf_without_a_note_or_a_rest() -> None:
    """A bare leaf, an emptied note carrier's leaf and a rest carrier's leaf without its
    rest; a group, however empty, is not a leaf's business."""
    score: Score = build_score(measure_count=1)
    group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    bare: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.voice,
        anchor=anchor_at(score=score, at=_Q),
        size=size(RhythmicValue.QUARTER),
    )
    emptied: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    assert isinstance(emptied.carrier, NoteCarrier)
    emptied.carrier.notes[0].detach()
    restless: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.voice,
        anchor=anchor_at(score=score, at=Fraction(3, 4)),
        size=size(RhythmicValue.QUARTER),
    )
    RestCarrier.create(owner=restless)

    fixes: Sequence[DeleteRequest] = EmptyLeavesPostprocessor().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    )

    assert [fix.target for fix in fixes] == [bare, emptied, restless]


def _rests(*, score: Score, parent: GroupRhythmicContainer, at: Fraction) -> None:
    """Three triplet eighth rests filling ``parent`` from ``at``."""
    for index in range(3):
        Rest.create(
            rest_carrier=RestCarrier.create(
                owner=LeafRhythmicContainer.create(
                    parent=parent,
                    anchor=anchor_at(score=score, at=at + Fraction(index, 12)),
                    size=size(RhythmicValue.EIGHTH),
                )
            ),
            staff=score.staff,
        )


@pytest.mark.unit
def test_the_empty_groups_post_reports_an_empty_group_only_where_its_voice_holds_nothing() -> None:
    """Measure one holds a note: its empty group stays. Measure two holds nothing but an
    empty group nested in another: only the outer one is reported, its cascade takes the
    inner. Measure three holds a group of rests, which is content."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0, beats=(0,))
    beside: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    group(
        score=score,
        parent=outer,
        at=Fraction(1),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    of_rests: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(2),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    _rests(score=score, parent=of_rests, at=Fraction(2))

    fixes: Sequence[DeleteRequest] = EmptyGroupsPostprocessor().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    )

    assert [fix.target for fix in fixes] == [outer]
    assert beside in score.voice.children


@pytest.mark.unit
def test_the_empty_groups_post_judges_a_group_by_every_measure_it_reaches() -> None:
    """An empty group across the barline, its voice holding a note only in the second
    measure: the group reaches that measure, so it stays."""
    score: Score = build_score(measure_count=2)
    group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    quarters(score=score, measure=1, beats=(3,))

    assert (
        EmptyGroupsPostprocessor().search_fixes(
            document=score.document,
            geometry=ScoreGeometry(document=score.document),
        )
        == []
    )


@pytest.mark.unit
def test_the_empty_groups_post_does_not_judge_a_group_by_the_measure_after_its_end() -> None:
    """An empty group ending exactly on the barline, its voice holding a note only in the
    second measure: the group does not reach that measure, so it is reported."""
    score: Score = build_score(measure_count=2)
    empty: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    quarters(score=score, measure=1, beats=(0,))

    fixes: Sequence[DeleteRequest] = EmptyGroupsPostprocessor().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    )

    assert [fix.target for fix in fixes] == [empty]


@pytest.mark.unit
def test_the_orphan_anchors_post_reports_only_anchors_nothing_starts_at() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    orphan: TemporalAnchor = anchor_at(score=score, at=_Q)

    fixes: Sequence[DeleteRequest] = OrphanAnchorsPostprocessor().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    )

    assert [fix.target for fix in fixes] == [orphan]


# --- the anchor analyzer --------------------------------------------------------------


@pytest.mark.unit
def test_the_anchor_analyzer_refuses_a_position_another_anchor_already_holds() -> None:
    """A position is storage shared by everything starting there: finding the anchor that is
    there is the caller's job (``find_or_create_anchor``), creating a second one is a broken
    invariant."""
    score: Score = build_score(measure_count=1, start_contexts=False)
    anchor_at(score=score, at=_Q)

    with pytest.raises(ValueError, match="already stands here"):
        _engine(analyzer_registry=_create_chain_analyzers()).process(
            document=score.document,
            requests=[_anchor_request_at(score=score, at=_Q)],
        )

    assert [anchor.position.value for anchor in score.measures[0].anchors] == [_Q]


# --- one gesture, one journal ---------------------------------------------------------


@pytest.mark.unit
def test_rolling_back_a_displacing_gesture_restores_the_group() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))
    before = layout(score=score)

    log: MutationLog = _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)
    log.rollback()

    assert layout(score=score) == before
    assert len(score.measures[0].anchors) == 6


# --- the guards: the end of a pass -----------------------------------------------------


class _RecordingGuard(InvariantGuard):
    """Records how many anchors the first measure holds each time it is asked; returns
    ``fixes`` once, the first time."""

    def __init__(self, *, score: Score, fixes: Sequence[MutationRequest] = ()) -> None:
        self._score: Score = score
        self._fixes: list[MutationRequest] = list(fixes)
        self.seen: list[int] = []

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[MutationRequest]:
        self.seen.append(len(self._score.measures[0].anchors))
        fixes: list[MutationRequest] = self._fixes
        self._fixes = []

        return fixes


class _AnchorPost(MutatedStatePostprocessor):
    """A post that asks for one anchor on beat three of the first measure."""

    def __init__(self, *, score: Score) -> None:
        self._score: Score = score

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[CreateTemporalAnchorRequest]:
        return [_anchor_request_at(score=self._score, at=_H)]


def _anchor_request_at(*, score: Score, at: Fraction) -> CreateTemporalAnchorRequest:
    return CreateTemporalAnchorRequest(
        measure=score.measures[0],
        position=MeasurePosition.of_fraction(fraction=at),
    )


def _guarded_engine(
    *,
    analyzer_registry: MutationAnalyzerRegistry,
    postprocessors: list[MutatedStatePostprocessor],
    guard: InvariantGuard,
) -> MutationEngine:
    """The real handlers, the given analyzers and posts, and one guard."""
    return MutationEngine(
        handler_registry=build_handler_registry(),
        analyzer_registry=analyzer_registry,
        postprocessors=postprocessors,
        guards=[guard],
    )


@pytest.mark.unit
def test_the_guards_run_once_after_all_the_requests_of_a_pass() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    guard: _RecordingGuard = _RecordingGuard(score=score)

    _guarded_engine(
        analyzer_registry=_create_chain_analyzers(),
        postprocessors=[],
        guard=guard,
    ).process(
        document=score.document,
        requests=[
            _anchor_request_at(score=score, at=Fraction(0)),
            _anchor_request_at(score=score, at=_Q),
        ],
    )

    assert guard.seen == [2]


@pytest.mark.unit
def test_the_guards_do_not_run_between_the_steps_of_an_intent_request() -> None:
    """The steps an intent yields run one after the other with no guard between them; the
    guard runs once, when the pass ends."""
    score: Score = build_score(measure_count=1, start_contexts=False)
    guard: _RecordingGuard = _RecordingGuard(score=score)

    def remove(request: RemoveRequest) -> MutationAnalysis:
        yield _anchor_request_at(score=score, at=Fraction(0))
        assert guard.seen == []
        yield _anchor_request_at(score=score, at=_Q)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(request_type=RemoveRequest, analyzer=_ScriptedAnalyzer(script=remove))

    _guarded_engine(analyzer_registry=analyzers, postprocessors=[], guard=guard).process(
        document=score.document,
        requests=[RemoveRequest(document=score.document, targets=())],
    )

    assert guard.seen == [2]


@pytest.mark.unit
def test_the_guards_do_not_run_between_the_steps_of_a_request_below_intent() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    guard: _RecordingGuard = _RecordingGuard(score=score)

    def create_leaf(request: CreateLeafRequest) -> MutationAnalysis:
        anchor: ScoreEntity | None = yield _anchor_request_at(score=score, at=Fraction(0))
        yield _anchor_request_at(score=score, at=_Q)
        assert isinstance(anchor, TemporalAnchor)
        yield CreateLeafAction(parent=score.voice, anchor=anchor, size=request.written_size)

    analyzers: MutationAnalyzerRegistry = _create_chain_analyzers()
    analyzers.register(
        request_type=CreateLeafRequest, analyzer=_ScriptedAnalyzer(script=create_leaf)
    )

    _guarded_engine(analyzer_registry=analyzers, postprocessors=[], guard=guard).process(
        document=score.document,
        requests=[_leaf_request(score=score)],
    )

    assert guard.seen == [2]


@pytest.mark.unit
def test_the_guards_run_once_after_the_posts() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    guard: _RecordingGuard = _RecordingGuard(score=score)

    _guarded_engine(
        analyzer_registry=_create_chain_analyzers(),
        postprocessors=[_AnchorPost(score=score)],
        guard=guard,
    ).process(
        document=score.document,
        requests=[_anchor_request_at(score=score, at=Fraction(0))],
    )

    assert guard.seen == [2]


@pytest.mark.unit
def test_the_guards_fixes_are_not_judged_again() -> None:
    score: Score = build_score(measure_count=1, start_contexts=False)
    guard: _RecordingGuard = _RecordingGuard(
        score=score,
        fixes=[_anchor_request_at(score=score, at=_Q)],
    )

    _guarded_engine(
        analyzer_registry=_create_chain_analyzers(),
        postprocessors=[],
        guard=guard,
    ).process(
        document=score.document,
        requests=[_anchor_request_at(score=score, at=Fraction(0))],
    )

    assert guard.seen == [1]
    assert len(score.measures[0].anchors) == 2


@pytest.mark.unit
def test_the_relation_guard_repairs_relations_built_broken_and_then_finds_nothing() -> None:
    """Relations built on the model over a rest: a tie, a glissando and a beam of the three
    notes. An empty gesture still ends with the guards: the relation guard removes the tie
    and the glissando and cuts the beam to the two notes after the rest; then nothing is
    broken."""
    score: Score = build_score(measure_count=1)
    for index in (0, 2, 3):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=0,
        )
    rest(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH)
    rest(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF)
    first: Note = note_at(score=score, at=Fraction(0))
    third: Note = note_at(score=score, at=2 * _E)
    fourth: Note = note_at(score=score, at=3 * _E)
    Tie.create(start_note=first, end_note=third)
    Glissando.create(start_note=first, end_note=third, glissando_type=GlissandoType.STRAIGHT)
    beam: Beam = Beam.create(carriers=[first.note_carrier, third.note_carrier, fourth.note_carrier])
    assert len(broken_relations(score=score)) == 3

    build_engine().process(document=score.document, requests=[])

    assert list(first.relations) == []
    assert list(third.relations) == []
    assert list(beam.members) == [third.note_carrier, fourth.note_carrier]
    assert list(first.note_carrier.carrier_group_relations) == []
    assert broken_relations(score=score) == []
