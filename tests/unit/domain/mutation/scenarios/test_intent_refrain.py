import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import MeasurePosition, TemporalAnchor
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateRefrainIntent,
    DeleteBatchIntent,
    EditIntent,
    MoveRefrainEndIntent,
    MoveRefrainStartIntent,
    SetRefrainTimesIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=5)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _refrain(
    *,
    document: ScoreDocument,
    first: int,
    last: int | None,
    times: int = 2,
) -> MutationLog:
    """A refrain over whole measures from ``first`` to the start of ``last`` (None: to the
    end)."""
    return _run(
        document=document,
        intent=CreateRefrainIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            end_measure_id=None if last is None else document.measures[last].id,
            end_position=None if last is None else _START,
            times=times,
        ),
    )


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


def test_a_refrain_over_two_measures_is_played_the_given_times_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()

    log: MutationLog = _refrain(document=document, first=0, last=2, times=3)

    (refrain,) = _refrains(document=document)
    assert refrain.times == 3
    assert refrain.start.measure is document.measures[0]
    assert refrain.end is not None
    assert refrain.end.measure is document.measures[2]
    assert refrain.jump in refrain.end.departing_jumps

    log.rollback()
    assert _refrains(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_a_refrain_with_no_end_lasts_until_the_end_of_the_score() -> None:
    document: ScoreDocument = _document()

    _refrain(document=document, first=1, last=None)

    (refrain,) = _refrains(document=document)
    assert refrain.end is None


def test_refrains_may_touch_and_lie_inside_one_another_but_not_partly_over_each_other() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=1)
    _refrain(document=document, first=1, last=3)
    _refrain(document=document, first=0, last=4)
    _refrain(document=document, first=2, last=3)

    assert len(_refrains(document=document)) == 4
    with pytest.raises(MutationRejectedError, match="partly over"):
        _refrain(document=document, first=2, last=4)


def test_a_second_refrain_over_the_very_same_bars_is_refused() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=1, last=3)
    listed: int = _jumps_listed(document=document)

    with pytest.raises(MutationRejectedError, match="exactly the same bars"):
        _refrain(document=document, first=1, last=3, times=3)

    (refrain,) = _refrains(document=document)
    assert refrain.times == 2
    assert _jumps_listed(document=document) == listed


def test_a_refrain_must_end_after_it_starts_and_be_played_twice() -> None:
    document: ScoreDocument = _document()

    with pytest.raises(MutationRejectedError, match="end after it starts"):
        _refrain(document=document, first=2, last=1)

    with pytest.raises(MutationRejectedError, match="at least twice"):
        _refrain(document=document, first=0, last=1, times=1)

    assert _refrains(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_changing_the_times_keeps_the_refrain_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=1)
    (refrain,) = _refrains(document=document)

    log: MutationLog = _run(
        document=document, intent=SetRefrainTimesIntent(refrain_id=refrain.id, times=4)
    )

    assert _refrains(document=document) == [refrain]
    assert refrain.times == 4

    log.rollback()
    assert refrain.times == 2

    with pytest.raises(MutationRejectedError, match="at least twice"):
        _run(document=document, intent=SetRefrainTimesIntent(refrain_id=refrain.id, times=1))


def test_deleting_a_refrain_takes_its_jump_and_its_barlines_with_it() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=1, last=3)
    (refrain,) = _refrains(document=document)

    log: MutationLog = _run(document=document, intent=DeleteBatchIntent(entity_ids=(refrain.id,)))

    assert _refrains(document=document) == []
    assert _jumps_listed(document=document) == 0
    assert not document.measures[3].anchors

    log.rollback()
    assert _refrains(document=document) == [refrain]


def test_moving_the_end_of_a_refrain_keeps_it_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=2)
    (refrain,) = _refrains(document=document)

    moved: MutationLog = _run(
        document=document,
        intent=MoveRefrainEndIntent(
            refrain_id=refrain.id, measure_id=document.measures[3].id, position=_START
        ),
    )

    assert _refrains(document=document) == [refrain]
    assert refrain.end is not None
    assert refrain.end.measure is document.measures[3]
    assert refrain.jump in refrain.end.departing_jumps

    opened: MutationLog = _run(
        document=document,
        intent=MoveRefrainEndIntent(refrain_id=refrain.id, measure_id=None, position=None),
    )
    end_after_opening: TemporalAnchor | None = refrain.end

    opened.rollback()
    end_after_undoing_it: TemporalAnchor | None = refrain.end

    moved.rollback()
    end_after_undoing_both: TemporalAnchor | None = refrain.end

    assert end_after_opening is None
    assert end_after_undoing_it is not None
    assert end_after_undoing_it.measure is document.measures[3]
    assert end_after_undoing_both is not None
    assert end_after_undoing_both.measure is document.measures[2]


def test_moving_the_start_of_a_refrain_keeps_it_and_its_jump() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=1, last=3)
    (refrain,) = _refrains(document=document)

    _run(
        document=document,
        intent=MoveRefrainStartIntent(
            refrain_id=refrain.id, measure_id=document.measures[2].id, position=_START
        ),
    )

    assert _refrains(document=document) == [refrain]
    assert refrain.start.measure is document.measures[2]
    assert refrain.jump.target is refrain.start
    assert refrain.jump in refrain.start.arriving_jumps
    assert _jumps_listed(document=document) == 2


def test_a_refrain_cannot_be_moved_past_its_other_end_or_across_another_repeat() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=2)
    _refrain(document=document, first=3, last=None)
    first, second = _refrains(document=document)

    with pytest.raises(MutationRejectedError, match="end after it starts"):
        _run(
            document=document,
            intent=MoveRefrainEndIntent(
                refrain_id=first.id, measure_id=document.measures[0].id, position=_START
            ),
        )

    with pytest.raises(MutationRejectedError, match="partly over"):
        _run(
            document=document,
            intent=MoveRefrainEndIntent(
                refrain_id=first.id, measure_id=document.measures[4].id, position=_START
            ),
        )

    assert first.end is not None
    assert first.end.measure is document.measures[2]
    assert second.start.measure is document.measures[3]
