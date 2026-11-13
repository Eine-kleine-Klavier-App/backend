from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain, Volta
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateRefrainIntent,
    CreateVoltaIntent,
    EditIntent,
    RemoveMeasureIntent,
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=7)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _remove(*, document: ScoreDocument, measure: int) -> MutationLog:
    return _run(
        document=document, intent=RemoveMeasureIntent(measure_id=document.measures[measure].id)
    )


def _volta(
    *,
    document: ScoreDocument,
    first: int,
    body_end: int,
    fragments: list[tuple[int, tuple[int, ...]]],
) -> Volta:
    _run(
        document=document,
        intent=CreateVoltaIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            body_end_measure_id=document.measures[body_end].id,
            body_end_position=_START,
            fragments=tuple(
                VoltaFragmentIntent(
                    end_measure_id=document.measures[end].id,
                    end_position=_START,
                    passes=passes,
                )
                for end, passes in fragments
            ),
        ),
    )
    return _voltas(document=document)[0]


def _refrain(*, document: ScoreDocument, first: int, last: int | None) -> Refrain:
    _run(
        document=document,
        intent=CreateRefrainIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            end_measure_id=None if last is None else document.measures[last].id,
            end_position=None if last is None else _START,
            times=2,
        ),
    )
    return _refrains(document=document)[0]


def _voltas(*, document: ScoreDocument) -> list[Volta]:
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Volta)
    ]


def _refrains(*, document: ScoreDocument) -> list[Refrain]:
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Refrain)
    ]


def _jumps_listed(*, document: ScoreDocument) -> int:
    return sum(
        len(anchor.departing_jumps) + len(anchor.arriving_jumps)
        for measure in document.measures
        for anchor in measure.anchors
    )


def _passes(*, volta: Volta) -> list[frozenset[int]]:
    return [fragment.passes for fragment in volta.fragments]


def test_removing_the_bar_of_an_ending_takes_the_ending_with_its_passes() -> None:
    """[1., 3. over measure 2 and [2. over measure 3: removing measure 2 takes the first."""
    document: ScoreDocument = _document()
    volta: Volta = _volta(
        document=document, first=0, body_end=2, fragments=[(3, (1, 3)), (4, (2,))]
    )

    log: MutationLog = _remove(document=document, measure=2)

    assert len(document.measures) == 6
    assert _voltas(document=document) == [volta]
    assert _passes(volta=volta) == [frozenset({1})]
    assert volta.pass_count == 2
    assert _jumps_listed(document=document) == 2 * len(volta.rules)

    log.rollback()
    assert len(document.measures) == 7
    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2})]
    assert volta.pass_count == 4


def test_removing_a_bar_inside_the_body_leaves_the_volta_as_it_is() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (4, (2,))])

    _remove(document=document, measure=1)

    assert _voltas(document=document) == [volta]
    assert _passes(volta=volta) == [frozenset({1}), frozenset({2})]
    assert volta.pass_count == 3


def test_removing_the_only_ending_leaves_no_volta_and_the_other_bars_stay() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,))])

    _remove(document=document, measure=2)

    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0
    assert len(document.measures) == 6


def test_removing_the_bars_of_the_body_shrinks_it_and_then_takes_the_volta() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _volta(document=document, first=0, body_end=2, fragments=[(3, (1,))])

    _remove(document=document, measure=0)
    assert _voltas(document=document) == [volta]
    assert volta.start.measure is document.measures[0]

    _remove(document=document, measure=0)
    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_the_last_ending_lasts_to_the_end_of_the_score_once_its_barline_goes() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _volta(document=document, first=0, body_end=2, fragments=[(6, (1,))])

    _remove(document=document, measure=6)

    assert _voltas(document=document) == [volta]
    assert volta.fragments[-1].end is None
    assert _passes(volta=volta) == [frozenset({1})]


def test_removing_the_first_bar_of_a_refrain_shrinks_it_and_the_last_takes_it() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=1, last=3)

    _remove(document=document, measure=1)

    assert _refrains(document=document) == [refrain]
    assert refrain.start.measure is document.measures[1]
    assert refrain.jump.target is refrain.start
    assert refrain.times == 2

    _remove(document=document, measure=1)

    assert _refrains(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_a_refrain_whose_end_barline_goes_ends_at_the_start_of_the_next_measure() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=0, last=2)

    log: MutationLog = _remove(document=document, measure=2)

    assert refrain.end is not None
    assert refrain.end.measure is document.measures[2]
    assert refrain.jump in refrain.end.departing_jumps

    log.rollback()
    assert refrain.end is not None
    assert refrain.end.measure is document.measures[2]
    assert len(document.measures) == 7


def test_a_refrain_in_the_last_measure_goes_with_it() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=6, last=None)

    _remove(document=document, measure=6)

    assert _refrains(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_a_refrain_that_lasts_to_the_end_of_the_score_stays_when_the_last_bar_goes() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=3, last=None)

    _remove(document=document, measure=6)

    assert _refrains(document=document) == [refrain]
    assert refrain.end is None
