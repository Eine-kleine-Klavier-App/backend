from collections.abc import Callable
from fractions import Fraction

from piano_app.domain.score.document.models.context import NewFragment, Volta
from piano_app.domain.score.document.models.context.point.volta import check_fragment_passes
from piano_app.domain.score.document.models.structural import MEASURE_START, TemporalAnchor
from piano_app.domain.score.document.services.contexts import ContextIndex, global_position
from piano_app.domain.score.document.services.contexts.repeat_nesting import (
    Piece,
    check_nesting,
    pieces_of_elements,
)
from piano_app.domain.score.document.services.contexts.volta_layout import (
    Boundary,
    Layout,
    append_fragment,
    collapse,
    move_boundary,
    move_start,
    set_passes,
    set_times,
    split_last_fragment,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateVoltaAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    AppendVoltaFragmentRequest,
    CollapseVoltaRequest,
    CreateVoltaRequest,
    MoveVoltaBoundaryRequest,
    MoveVoltaStartRequest,
    SetVoltaFragmentPassesRequest,
    SetVoltaTimesRequest,
    SplitVoltaFragmentRequest,
)

from .volta_reshape import Ref, Spot, boundary_at, layout_of, reshape_volta


class CreateVoltaAnalyzer:
    """Decides placement for the endings of a repeat. Every end is reused or created, the end
    of the last fragment only when it is given: without one it lasts until the end of the
    score.

    The body must end after it starts and each fragment after the one before it, only the
    last one may last to the end of the score, the fragments must hold every pass from the
    first, each in one, and the volta may not lie partly over another repeat or volta; all of
    it is refused before anything is created.
    """

    def analyze(
        self,
        *,
        request: CreateVoltaRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        try:
            check_fragment_passes(passes=[fragment.passes for fragment in request.fragments])
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        start: Fraction = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        body_end: Fraction = global_position(
            geometry=geometry,
            measure=request.body_end_measure,
            position=request.body_end_position,
        )
        if body_end <= start:
            raise MutationRejectedError("The body of a volta must end after it starts.")

        pieces: list[Piece] = [Piece(start=start, end=body_end)]
        previous: Fraction = body_end
        for index, fragment in enumerate(request.fragments):
            end: Fraction
            if fragment.end_measure is None or fragment.end_position is None:
                if index != len(request.fragments) - 1:
                    raise MutationRejectedError(
                        "Only the last fragment of a volta lasts to the end of the score."
                    )

                end = geometry.root.extent
            else:
                end = global_position(
                    geometry=geometry, measure=fragment.end_measure, position=fragment.end_position
                )

            if end <= previous:
                raise MutationRejectedError("A fragment of a volta must end after it starts.")

            pieces.append(Piece(start=previous, end=end))
            previous = end

        try:
            check_nesting(
                elements=[*pieces_of_elements(geometry=geometry, contexts=contexts), pieces]
            )
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        body_end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.body_end_measure, position=request.body_end_position
        )
        fragments: list[NewFragment] = []
        for fragment in request.fragments:
            end_anchor: TemporalAnchor | None = None
            if fragment.end_measure is not None and fragment.end_position is not None:
                end_anchor = yield from find_or_create_anchor(
                    measure=fragment.end_measure, position=fragment.end_position
                )

            fragments.append(NewFragment(end=end_anchor, passes=fragment.passes))

        yield CreateVoltaAction(
            start=start_anchor, body_end=body_end_anchor, fragments=tuple(fragments)
        )


def _planned(
    *,
    volta: Volta,
    geometry: ScoreGeometry,
    plan: Callable[[Layout[Ref]], Layout[Ref] | None],
) -> Layout[Ref] | None:
    """The layout a change of the volta leads to; what the layout refuses is refused."""
    try:
        return plan(layout_of(volta=volta, geometry=geometry))
    except ValueError as error:
        raise MutationRejectedError(str(error)) from error


class MoveVoltaBoundaryAnalyzer:
    """Drags a boundary of a volta: the fragments the dragged boundary covers whole are
    absorbed, with their passes, and the later passes shift down; with no fragment left the
    volta goes and its bars stay."""

    def analyze(
        self,
        *,
        request: MoveVoltaBoundaryRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        to = boundary_at(geometry=geometry, measure=request.measure, position=request.position)
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: move_boundary(layout=current, index=request.boundary, to=to),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class MoveVoltaStartAnalyzer:
    """Moves the start of the body of a volta; only the body changes."""

    def analyze(
        self,
        *,
        request: MoveVoltaStartRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        to = boundary_at(geometry=geometry, measure=request.measure, position=request.position)
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: move_start(layout=current, to=to),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class SetVoltaFragmentPassesAnalyzer:
    """Sets the passes of a fragment of a volta; the first fragment is played in whatever the
    others leave."""

    def analyze(
        self,
        *,
        request: SetVoltaFragmentPassesRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: set_passes(
                layout=current, index=request.fragment, passes=request.passes
            ),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class SetVoltaTimesAnalyzer:
    """Sets how many times a volta is played: the first fragment takes the passes the others
    leave."""

    def analyze(
        self,
        *,
        request: SetVoltaTimesRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: set_times(layout=current, times=request.times),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class AppendVoltaFragmentAnalyzer:
    """Adds a fragment after the last one of a volta; it is played in the pass that was the
    last one."""

    def analyze(
        self,
        *,
        request: AppendVoltaFragmentRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        end = boundary_at(geometry=geometry, measure=request.measure, position=request.position)
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: append_fragment(layout=current, end=end),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class SplitVoltaFragmentAnalyzer:
    """Cuts the last fragment of a volta in two; the second part is played in the pass that
    was the last one."""

    def analyze(
        self,
        *,
        request: SplitVoltaFragmentRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        at = boundary_at(geometry=geometry, measure=request.measure, position=request.position)
        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: split_last_fragment(layout=current, at=at),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )


class CollapseVoltaAnalyzer:
    """Draws the boundaries of a volta that lie in a measure about to be removed to where the
    measure ends. A fragment left with no length goes with its passes and the later passes
    shift down; a volta left with no body or no fragment is deleted and its bars stay."""

    def analyze(
        self,
        *,
        request: CollapseVoltaRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        measure_end = geometry.measure_span(measure=request.measure).end
        after = request.measure.next_measure
        to: Boundary[Ref] = Boundary(
            position=measure_end,
            ref=None if after is None else Spot(measure=after, position=MEASURE_START),
        )

        def inside(ref: Ref) -> bool:
            return isinstance(ref, TemporalAnchor) and ref.measure is request.measure

        layout: Layout[Ref] | None = _planned(
            volta=request.target,
            geometry=geometry,
            plan=lambda current: collapse(layout=current, inside=inside, to=to),
        )

        yield from reshape_volta(
            volta=request.target, layout=layout, geometry=geometry, contexts=contexts
        )
