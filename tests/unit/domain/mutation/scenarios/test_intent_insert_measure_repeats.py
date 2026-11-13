from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain, Volta
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateRefrainIntent,
    CreateVoltaIntent,
    EditIntent,
    InsertMeasureIntent,
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=6)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _refrain(*, document: ScoreDocument, first: int, last: int) -> Refrain:
    """A refrain over whole measures from ``first`` to the start of ``last``."""
    _run(
        document=document,
        intent=CreateRefrainIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            end_measure_id=document.measures[last].id,
            end_position=_START,
            times=2,
        ),
    )
    (refrain,) = [
        context
        for anchor in document.measures[first].anchors
        for context in anchor.starting_contexts
        if isinstance(context, Refrain)
    ]
    return refrain


def _insert_before(*, document: ScoreDocument, measure: Measure) -> MutationLog:
    return _run(document=document, intent=InsertMeasureIntent(before_measure_id=measure.id))


def test_a_measure_added_after_a_repeat_stays_outside_it_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=1, last=3)
    after: Measure = document.measures[3]

    log: MutationLog = _insert_before(document=document, measure=after)

    assert refrain.start.measure is document.measures[1]
    assert refrain.end is not None
    assert refrain.end.measure is document.measures[3]
    assert document.measures[4] is after
    assert refrain.end.measure is not after

    log.rollback()
    assert refrain.end is not None
    assert refrain.end.measure is after


def test_a_measure_added_inside_a_repeat_or_before_it_leaves_the_repeat_ends_alone() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=1, last=4)
    first, inner, last = document.measures[1], document.measures[2], document.measures[4]

    _insert_before(document=document, measure=inner)
    assert refrain.start.measure is first
    assert refrain.end is not None
    assert refrain.end.measure is last

    _insert_before(document=document, measure=first)
    assert refrain.start.measure is first
    assert refrain.end.measure is last


def test_a_measure_added_between_two_repeats_in_a_row_lies_between_them() -> None:
    document: ScoreDocument = _document()
    left: Refrain = _refrain(document=document, first=0, last=2)
    right: Refrain = _refrain(document=document, first=2, last=4)
    between: Measure = document.measures[2]

    _insert_before(document=document, measure=between)

    assert left.end is not None
    assert left.end.measure is document.measures[2]
    assert right.start.measure is between
    assert document.measures[3] is between


def test_a_measure_added_after_a_volta_stays_outside_it() -> None:
    document: ScoreDocument = _document()
    _run(
        document=document,
        intent=CreateVoltaIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            body_end_measure_id=document.measures[2].id,
            body_end_position=_START,
            fragments=(
                VoltaFragmentIntent(
                    end_measure_id=document.measures[3].id,
                    end_position=_START,
                    passes=(1,),
                ),
            ),
        ),
    )
    (volta,) = [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Volta)
    ]
    after: Measure = document.measures[3]
    body_end = volta.body_end

    _insert_before(document=document, measure=after)

    (fragment,) = volta.fragments
    assert fragment.end is not None
    assert fragment.end.measure is document.measures[3]
    assert document.measures[4] is after
    assert volta.body_end is body_end
