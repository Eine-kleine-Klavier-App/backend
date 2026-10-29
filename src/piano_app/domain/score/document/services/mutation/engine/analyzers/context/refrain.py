from fractions import Fraction

from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, global_position
from piano_app.domain.score.document.services.contexts.repeat_nesting import (
    Piece,
    check_nesting,
    pieces_of_elements,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateRefrainAction,
    UpdateRefrainEndAction,
    UpdateRefrainStartAction,
    UpdateRefrainTimesAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CollapseRefrainRequest,
    CreateRefrainRequest,
    MoveRefrainEndRequest,
    MoveRefrainStartRequest,
    UpdateRefrainTimesRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


def _refuse_bad_times(*, times: int) -> None:
    if times < 2:
        raise MutationRejectedError("A refrain is played at least twice.")


class CreateRefrainAnalyzer:
    """Decides placement for a new refrain. Both ends are reused or created, the end only when
    it is given: without one the refrain lasts until the end of the score.

    It must end after it starts and may not lie partly over another repeat or volta; both are
    refused before anything is created. Repeats may touch and may lie inside one another.
    """

    def analyze(
        self,
        *,
        request: CreateRefrainRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        _refuse_bad_times(times=request.times)

        start: Fraction = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        end: Fraction
        if request.end_measure is None or request.end_position is None:
            end = geometry.root.extent
        else:
            end = global_position(
                geometry=geometry, measure=request.end_measure, position=request.end_position
            )
        if end <= start:
            raise MutationRejectedError("A refrain must end after it starts.")

        try:
            check_nesting(
                elements=[
                    *pieces_of_elements(geometry=geometry, contexts=contexts),
                    [Piece(start=start, end=end)],
                ]
            )
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        end_anchor: TemporalAnchor | None = None
        if request.end_measure is not None and request.end_position is not None:
            end_anchor = yield from find_or_create_anchor(
                measure=request.end_measure, position=request.end_position
            )

        yield CreateRefrainAction(start=start_anchor, end=end_anchor, times=request.times)


class UpdateRefrainTimesAnalyzer:
    """Changes how many times a refrain is played; the refrain itself stays."""

    def analyze(
        self,
        *,
        request: UpdateRefrainTimesRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        _refuse_bad_times(times=request.times)

        yield UpdateRefrainTimesAction(target=request.target, times=request.times)


def _refuse_bad_move(
    *,
    refrain: Refrain,
    start: Fraction,
    end: Fraction,
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> None:
    """A refrain must end after it starts and, placed as asked, not lie partly over another."""
    if end <= start:
        raise MutationRejectedError("A refrain must end after it starts.")

    try:
        check_nesting(
            elements=[
                *pieces_of_elements(geometry=geometry, contexts=contexts, without=refrain),
                [Piece(start=start, end=end)],
            ]
        )
    except ValueError as error:
        raise MutationRejectedError(str(error)) from error


class MoveRefrainStartAnalyzer:
    """Moves the start of a refrain; the refrain itself stays."""

    def analyze(
        self,
        *,
        request: MoveRefrainStartRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        refrain: Refrain = request.target
        _refuse_bad_move(
            refrain=refrain,
            start=global_position(
                geometry=geometry, measure=request.measure, position=request.position
            ),
            end=geometry.root.extent
            if refrain.end is None
            else geometry.point_of(anchor=refrain.end).value,
            geometry=geometry,
            contexts=contexts,
        )

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield UpdateRefrainStartAction(target=refrain, start=start_anchor)


class MoveRefrainEndAnalyzer:
    """Moves the end of a refrain, or lets it last until the end of the score; the refrain
    itself stays."""

    def analyze(
        self,
        *,
        request: MoveRefrainEndRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        refrain: Refrain = request.target
        end: Fraction = (
            geometry.root.extent
            if request.measure is None or request.position is None
            else global_position(
                geometry=geometry, measure=request.measure, position=request.position
            )
        )
        _refuse_bad_move(
            refrain=refrain,
            start=geometry.point_of(anchor=refrain.start).value,
            end=end,
            geometry=geometry,
            contexts=contexts,
        )

        end_anchor: TemporalAnchor | None = None
        if request.measure is not None and request.position is not None:
            end_anchor = yield from find_or_create_anchor(
                measure=request.measure, position=request.position
            )

        yield UpdateRefrainEndAction(target=refrain, end=end_anchor)


class CollapseRefrainAnalyzer:
    """Draws the ends of a refrain that lie in a measure about to be removed to where the
    measure ends: the start moves to the start of the next measure, the end too or, when the
    measure is the last, to the end of the score. A refrain left with no length is deleted."""

    def analyze(
        self,
        *,
        request: CollapseRefrainRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        refrain: Refrain = request.target
        measure_end: Fraction = geometry.measure_span(measure=request.measure).end
        start_inside: bool = refrain.start.measure is request.measure
        end_inside: bool = refrain.end is not None and refrain.end.measure is request.measure

        start: Fraction = (
            measure_end if start_inside else geometry.point_of(anchor=refrain.start).value
        )
        end: Fraction = (
            geometry.root.extent
            if refrain.end is None
            else (measure_end if end_inside else geometry.point_of(anchor=refrain.end).value)
        )
        if end <= start:
            yield DeleteRequest(target=refrain)
            return

        boundary: Measure | None = request.measure.next_measure
        if end_inside:
            end_anchor: TemporalAnchor | None = None
            if boundary is not None:
                end_anchor = yield from find_or_create_anchor(
                    measure=boundary, position=MEASURE_START
                )

            yield UpdateRefrainEndAction(target=refrain, end=end_anchor)

        if start_inside and boundary is not None:
            start_anchor: TemporalAnchor = yield from find_or_create_anchor(
                measure=boundary, position=MEASURE_START
            )

            yield UpdateRefrainStartAction(target=refrain, start=start_anchor)
