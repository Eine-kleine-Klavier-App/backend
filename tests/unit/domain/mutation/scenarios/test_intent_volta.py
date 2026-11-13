import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain, Volta, VoltaFragment
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AddRefrainEndingIntent,
    AppendVoltaFragmentIntent,
    CreateRefrainIntent,
    CreateVoltaIntent,
    DeleteBatchIntent,
    EditIntent,
    MoveVoltaBoundaryIntent,
    MoveVoltaStartIntent,
    SetVoltaFragmentPassesIntent,
    SetVoltaTimesIntent,
    SplitVoltaFragmentIntent,
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)

type Fragments = list[tuple[int | None, tuple[int, ...]]]


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=7)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _volta(
    *,
    document: ScoreDocument,
    first: int,
    body_end: int,
    fragments: Fragments,
) -> MutationLog:
    """A volta whose body lies over whole measures from ``first`` to the start of
    ``body_end``, and whose fragments end at the start of the given measures (None: the end of
    the score), each with its passes."""
    return _run(
        document=document,
        intent=CreateVoltaIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            body_end_measure_id=document.measures[body_end].id,
            body_end_position=_START,
            fragments=tuple(
                VoltaFragmentIntent(
                    end_measure_id=None if end is None else document.measures[end].id,
                    end_position=None if end is None else _START,
                    passes=passes,
                )
                for end, passes in fragments
            ),
        ),
    )


def _refrain(*, document: ScoreDocument, first: int, last: int) -> MutationLog:
    return _run(
        document=document,
        intent=CreateRefrainIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            end_measure_id=document.measures[last].id,
            end_position=_START,
            times=2,
        ),
    )


def _voltas(*, document: ScoreDocument) -> list[Volta]:
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Volta)
    ]


def _jumps_listed(*, document: ScoreDocument) -> int:
    return sum(
        len(anchor.departing_jumps) + len(anchor.arriving_jumps)
        for measure in document.measures
        for anchor in measure.anchors
    )


def _passes(*, volta: Volta) -> list[frozenset[int]]:
    return [fragment.passes for fragment in volta.fragments]


def test_a_volta_of_two_endings_is_made_from_its_jumps_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()

    log: MutationLog = _volta(
        document=document, first=0, body_end=2, fragments=[(3, (1,)), (4, (2,))]
    )

    (volta,) = _voltas(document=document)
    assert volta.pass_count == 3
    assert _passes(volta=volta) == [frozenset({1}), frozenset({2})]
    assert volta.start.measure is document.measures[0]
    assert volta.body_end.measure is document.measures[2]
    assert [fragment.end.measure for fragment in volta.fragments if fragment.end] == [
        document.measures[3],
        document.measures[4],
    ]
    assert _jumps_listed(document=document) == 2 * len(volta.rules)

    log.rollback()
    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_an_ending_for_several_passes_leaves_the_first_ending_the_rest() -> None:
    document: ScoreDocument = _document()

    _volta(document=document, first=0, body_end=2, fragments=[(3, (1, 3)), (4, (2,))])

    (volta,) = _voltas(document=document)
    assert volta.pass_count == 4
    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2})]


def test_the_last_ending_may_last_to_the_end_of_the_score() -> None:
    document: ScoreDocument = _document()

    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (None, (2,))])

    (volta,) = _voltas(document=document)
    last: VoltaFragment = volta.fragments[-1]
    assert last.end is None


def test_endings_must_hold_every_pass_each_in_one() -> None:
    document: ScoreDocument = _document()

    with pytest.raises(MutationRejectedError, match="every pass from the first"):
        _volta(document=document, first=0, body_end=2, fragments=[(3, (1, 2)), (4, (2,))])

    with pytest.raises(MutationRejectedError, match="every pass from the first"):
        _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (4, (3,))])

    with pytest.raises(MutationRejectedError, match="at least one pass"):
        _volta(document=document, first=0, body_end=2, fragments=[(3, ())])

    with pytest.raises(MutationRejectedError, match="at least one fragment"):
        _volta(document=document, first=0, body_end=2, fragments=[])

    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_the_first_ending_cannot_leave_out_the_first_pass() -> None:
    document: ScoreDocument = _document()

    with pytest.raises(MutationRejectedError, match="after the first"):
        _volta(document=document, first=0, body_end=2, fragments=[(3, (2,)), (4, (1, 3))])

    assert _voltas(document=document) == []


def test_the_parts_of_a_volta_follow_one_another() -> None:
    document: ScoreDocument = _document()

    with pytest.raises(MutationRejectedError, match="body of a volta must end"):
        _volta(document=document, first=2, body_end=1, fragments=[(3, (1,))])

    with pytest.raises(MutationRejectedError, match="must end after it starts"):
        _volta(document=document, first=0, body_end=2, fragments=[(4, (1,)), (3, (2,))])

    with pytest.raises(MutationRejectedError, match="Only the last fragment"):
        _volta(document=document, first=0, body_end=2, fragments=[(None, (1,)), (4, (2,))])

    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0


def test_a_repeat_may_lie_inside_one_part_of_a_volta_but_not_across_two() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(4, (1,))])

    _refrain(document=document, first=0, last=1)
    _refrain(document=document, first=2, last=3)
    assert len(_voltas(document=document)) == 1

    with pytest.raises(MutationRejectedError, match="across its parts"):
        _refrain(document=document, first=1, last=3)


def test_a_second_volta_over_the_very_same_bars_is_refused() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=1, body_end=2, fragments=[(3, (1,))])

    with pytest.raises(MutationRejectedError, match="exactly the same bars"):
        _volta(document=document, first=1, body_end=2, fragments=[(3, (1,))])

    assert len(_voltas(document=document)) == 1


def test_a_refrain_and_a_volta_over_the_very_same_bars_are_refused_in_either_order() -> None:
    first: ScoreDocument = _document()
    _volta(document=first, first=1, body_end=2, fragments=[(3, (1,))])

    with pytest.raises(MutationRejectedError, match="exactly the same bars"):
        _refrain(document=first, first=1, last=3)

    second: ScoreDocument = _document()
    _refrain(document=second, first=1, last=3)

    with pytest.raises(MutationRejectedError, match="exactly the same bars"):
        _volta(document=second, first=1, body_end=2, fragments=[(3, (1,))])

    assert len(_voltas(document=first)) == 1
    assert len(_refrains(document=second)) == 1
    assert _voltas(document=second) == []


def test_an_ending_that_would_make_a_volta_over_the_bars_of_another_repeat_is_refused() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=1, last=2)
    _refrain(document=document, first=1, last=3)
    (short,) = [
        refrain
        for refrain in _refrains(document=document)
        if refrain.end is not None and refrain.end.measure is document.measures[2]
    ]

    with pytest.raises(MutationRejectedError, match="exactly the same bars"):
        _run(
            document=document,
            intent=AddRefrainEndingIntent(
                refrain_id=short.id, measure_id=document.measures[3].id, position=_START
            ),
        )

    assert len(_refrains(document=document)) == 2
    assert _voltas(document=document) == []


def test_a_repeat_may_surround_a_volta_but_not_cut_it() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=1, body_end=2, fragments=[(3, (1,))])

    _refrain(document=document, first=0, last=5)

    with pytest.raises(MutationRejectedError, match="partly over"):
        _refrain(document=document, first=2, last=6)


def test_deleting_a_volta_takes_all_its_jumps_and_barlines_with_it() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (4, (2,))])
    (volta,) = _voltas(document=document)

    log: MutationLog = _run(document=document, intent=DeleteBatchIntent(entity_ids=(volta.id,)))

    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0
    assert not document.measures[2].anchors
    assert not document.measures[4].anchors

    log.rollback()
    assert _voltas(document=document) == [volta]
    assert _passes(volta=volta) == [frozenset({1}), frozenset({2})]


def test_the_jump_elements_are_findable_by_their_kind() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,))])
    _refrain(document=document, first=4, last=5)

    kinds: list[type] = [
        type(context)
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Volta | Refrain)
    ]

    assert kinds == [Volta, Refrain]


def _four_passes(*, document: ScoreDocument) -> Volta:
    """[1., 3. over measure 2 and [2. over measure 3, the body being measures 0 and 1."""
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1, 3)), (4, (2,))])
    (volta,) = _voltas(document=document)
    return volta


def _end_measures(*, volta: Volta, document: ScoreDocument) -> list[int]:
    return [
        document.measures.index(fragment.end.measure)
        for fragment in volta.fragments
        if fragment.end is not None
    ]


def test_stretching_an_ending_over_the_next_absorbs_it_and_goes_with_an_undo() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    log: MutationLog = _run(
        document=document,
        intent=MoveVoltaBoundaryIntent(
            volta_id=volta.id, boundary=1, measure_id=document.measures[4].id, position=_START
        ),
    )

    assert _voltas(document=document) == [volta]
    assert _passes(volta=volta) == [frozenset({1, 2})]
    assert _end_measures(volta=volta, document=document) == [4]
    assert volta.pass_count == 3
    assert _jumps_listed(document=document) == 2 * len(volta.rules)

    log.rollback()
    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2})]
    assert volta.pass_count == 4


def test_an_ending_stretched_left_over_the_one_before_absorbs_that_one() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    _run(
        document=document,
        intent=MoveVoltaBoundaryIntent(
            volta_id=volta.id, boundary=1, measure_id=document.measures[2].id, position=_START
        ),
    )

    assert _passes(volta=volta) == [frozenset({1})]
    assert volta.pass_count == 2


def test_the_body_stretched_over_every_ending_leaves_no_volta_and_the_measures_stay() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    _run(
        document=document,
        intent=MoveVoltaBoundaryIntent(
            volta_id=volta.id, boundary=0, measure_id=document.measures[4].id, position=_START
        ),
    )

    assert _voltas(document=document) == []
    assert _jumps_listed(document=document) == 0
    assert len(document.measures) == 7


def test_the_body_cannot_be_left_with_nothing() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    with pytest.raises(MutationRejectedError, match="body of a volta must end"):
        _run(
            document=document,
            intent=MoveVoltaBoundaryIntent(
                volta_id=volta.id,
                boundary=0,
                measure_id=document.measures[0].id,
                position=_START,
            ),
        )

    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2})]


def test_the_end_of_the_last_ending_moves_alone_and_may_lead_to_the_end_of_the_score() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    _run(
        document=document,
        intent=MoveVoltaBoundaryIntent(
            volta_id=volta.id, boundary=2, measure_id=None, position=None
        ),
    )

    assert volta.fragments[-1].end is None
    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2})]


def test_the_start_of_the_body_moves_alone() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=1, body_end=3, fragments=[(4, (1,))])
    (volta,) = _voltas(document=document)

    _run(
        document=document,
        intent=MoveVoltaStartIntent(
            volta_id=volta.id, measure_id=document.measures[2].id, position=_START
        ),
    )

    assert _voltas(document=document) == [volta]
    assert volta.start.measure is document.measures[2]
    assert volta.body_end.measure is document.measures[3]
    assert _jumps_listed(document=document) == 2 * len(volta.rules)


def test_naming_the_passes_of_an_ending_leaves_the_first_ending_the_rest() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    _run(
        document=document,
        intent=SetVoltaFragmentPassesIntent(volta_id=volta.id, fragment=1, passes=(2, 3)),
    )

    assert _passes(volta=volta) == [frozenset({1}), frozenset({2, 3})]

    with pytest.raises(MutationRejectedError, match="the others leave"):
        _run(
            document=document,
            intent=SetVoltaFragmentPassesIntent(volta_id=volta.id, fragment=0, passes=(1,)),
        )


def test_an_ending_added_after_the_last_takes_the_last_pass() -> None:
    document: ScoreDocument = _document()
    volta: Volta = _four_passes(document=document)

    log: MutationLog = _run(
        document=document,
        intent=AppendVoltaFragmentIntent(
            volta_id=volta.id, measure_id=document.measures[5].id, position=_START
        ),
    )

    assert _passes(volta=volta) == [frozenset({1, 3}), frozenset({2}), frozenset({4})]
    assert volta.pass_count == 5
    assert _end_measures(volta=volta, document=document) == [3, 4, 5]

    log.rollback()
    assert volta.pass_count == 4


def test_the_last_ending_cut_in_two_gives_the_rest_the_last_pass() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (5, (2,))])
    (volta,) = _voltas(document=document)

    _run(
        document=document,
        intent=SplitVoltaFragmentIntent(
            volta_id=volta.id, measure_id=document.measures[4].id, position=_START
        ),
    )

    assert _passes(volta=volta) == [frozenset({1}), frozenset({2}), frozenset({3})]
    assert _end_measures(volta=volta, document=document) == [3, 4, 5]


def test_dragging_a_boundary_cannot_put_a_repeat_across_two_parts() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=1, fragments=[(3, (1,)), (5, (2,))])
    (volta,) = _voltas(document=document)
    _refrain(document=document, first=1, last=3)

    with pytest.raises(MutationRejectedError, match="across its parts"):
        _run(
            document=document,
            intent=MoveVoltaBoundaryIntent(
                volta_id=volta.id, boundary=1, measure_id=document.measures[2].id, position=_START
            ),
        )

    assert _end_measures(volta=volta, document=document) == [3, 5]


def test_naming_a_pass_another_ending_has_takes_it_from_that_ending_in_one_step() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,)), (4, (2, 3)), (5, (4,))])
    (volta,) = _voltas(document=document)

    log: MutationLog = _run(
        document=document,
        intent=SetVoltaFragmentPassesIntent(volta_id=volta.id, fragment=2, passes=(3, 4)),
    )

    assert _passes(volta=volta) == [frozenset({1}), frozenset({2}), frozenset({3, 4})]

    log.rollback()
    assert _passes(volta=volta) == [frozenset({1}), frozenset({2, 3}), frozenset({4})]

    with pytest.raises(MutationRejectedError, match="at least one pass"):
        _run(
            document=document,
            intent=SetVoltaFragmentPassesIntent(volta_id=volta.id, fragment=1, passes=(4,)),
        )


def _refrains(*, document: ScoreDocument) -> list[Refrain]:
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Refrain)
    ]


def _refrain_times(*, document: ScoreDocument, first: int, last: int | None, times: int) -> None:
    _run(
        document=document,
        intent=CreateRefrainIntent(
            start_measure_id=document.measures[first].id,
            start_position=_START,
            end_measure_id=None if last is None else document.measures[last].id,
            end_position=None if last is None else _START,
            times=times,
        ),
    )


def test_a_repeat_becomes_a_volta_with_a_first_ending_and_goes_back_with_an_undo() -> None:
    document: ScoreDocument = _document()
    _refrain_times(document=document, first=1, last=3, times=3)
    (refrain,) = _refrains(document=document)

    log: MutationLog = _run(
        document=document,
        intent=AddRefrainEndingIntent(
            refrain_id=refrain.id, measure_id=document.measures[4].id, position=_START
        ),
    )

    assert _refrains(document=document) == []
    (volta,) = _voltas(document=document)
    assert volta.start.measure is document.measures[1]
    assert volta.body_end.measure is document.measures[3]
    assert _passes(volta=volta) == [frozenset({1, 2})]
    assert volta.pass_count == 3
    assert _end_measures(volta=volta, document=document) == [4]

    log.rollback()
    assert _voltas(document=document) == []
    assert _refrains(document=document) == [refrain]
    assert refrain.times == 3


def test_a_repeat_that_lasts_to_the_end_of_the_score_has_no_bar_for_an_ending() -> None:
    document: ScoreDocument = _document()
    _refrain_times(document=document, first=1, last=None, times=2)
    (refrain,) = _refrains(document=document)

    with pytest.raises(MutationRejectedError, match="no bar for an ending"):
        _run(
            document=document,
            intent=AddRefrainEndingIntent(refrain_id=refrain.id, measure_id=None, position=None),
        )

    assert _refrains(document=document) == [refrain]
    assert _voltas(document=document) == []


def test_the_first_ending_must_end_after_the_repeat_and_a_failure_changes_nothing() -> None:
    document: ScoreDocument = _document()
    _refrain_times(document=document, first=1, last=3, times=2)
    (refrain,) = _refrains(document=document)

    with pytest.raises(MutationRejectedError, match="must end after it starts"):
        _run(
            document=document,
            intent=AddRefrainEndingIntent(
                refrain_id=refrain.id, measure_id=document.measures[3].id, position=_START
            ),
        )

    assert _refrains(document=document) == [refrain]
    assert _voltas(document=document) == []


def test_setting_how_many_times_a_volta_is_played_gives_the_first_ending_the_rest() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1,))])
    (volta,) = _voltas(document=document)

    log: MutationLog = _run(
        document=document, intent=SetVoltaTimesIntent(volta_id=volta.id, times=4)
    )

    assert volta.pass_count == 4
    assert _passes(volta=volta) == [frozenset({1, 2, 3})]

    log.rollback()
    assert volta.pass_count == 2
    assert _passes(volta=volta) == [frozenset({1})]


def test_a_volta_cannot_be_played_fewer_times_than_an_ending_needs_or_less_than_twice() -> None:
    document: ScoreDocument = _document()
    _volta(document=document, first=0, body_end=2, fragments=[(3, (1, 2)), (4, (3,))])
    (volta,) = _voltas(document=document)

    with pytest.raises(MutationRejectedError, match="no longer have"):
        _run(document=document, intent=SetVoltaTimesIntent(volta_id=volta.id, times=3))

    with pytest.raises(MutationRejectedError, match="at least twice"):
        _run(document=document, intent=SetVoltaTimesIntent(volta_id=volta.id, times=1))

    assert volta.pass_count == 4
