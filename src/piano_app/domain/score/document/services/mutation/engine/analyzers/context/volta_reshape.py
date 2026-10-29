from collections.abc import Generator
from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import NewFragment, Volta
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, global_position
from piano_app.domain.score.document.services.contexts.repeat_nesting import (
    Piece,
    check_nesting,
    pieces_of_elements,
)
from piano_app.domain.score.document.services.contexts.volta_layout import (
    Boundary,
    Fragment,
    Layout,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    ReshapeVoltaAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Spot:
    """A place of a measure that has no anchor yet, standing for it in a layout."""

    measure: Measure
    position: MeasurePosition


# what stands for a place in a layout: a barline there already is, a place to make one at, or
# the end of the score
type Ref = TemporalAnchor | Spot | None


def layout_of(*, volta: Volta, geometry: ScoreGeometry) -> Layout[Ref]:
    """The volta as it is, laid out on the timeline with its own barlines."""

    def boundary(anchor: TemporalAnchor | None) -> Boundary[Ref]:
        return Boundary(
            position=(
                geometry.root.extent if anchor is None else geometry.point_of(anchor=anchor).value
            ),
            ref=anchor,
        )

    return Layout(
        start=boundary(volta.start),
        body_end=boundary(volta.body_end),
        fragments=tuple(
            Fragment(end=boundary(fragment.end), passes=fragment.passes)
            for fragment in volta.fragments
        ),
    )


def boundary_at(
    *,
    geometry: ScoreGeometry,
    measure: Measure | None,
    position: MeasurePosition | None,
) -> Boundary[Ref]:
    """A place asked for: the measure position, or the end of the score when none is given."""
    if measure is None or position is None:
        return Boundary(position=geometry.root.extent, ref=None)

    return Boundary(
        position=global_position(geometry=geometry, measure=measure, position=position),
        ref=Spot(measure=measure, position=position),
    )


def _anchor_of(
    *,
    ref: Ref,
) -> Generator[MutationWorkItem, ScoreEntity | None, TemporalAnchor | None]:
    if isinstance(ref, Spot):
        return (yield from find_or_create_anchor(measure=ref.measure, position=ref.position))

    return ref


def reshape_volta(
    *,
    volta: Volta,
    layout: Layout[Ref] | None,
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> MutationAnalysis:
    """Lay a volta out as ``layout`` says: with none, the volta is deleted and its bars stay.
    A volta that would lie partly over another repeat is refused before anything is made."""
    if layout is None:
        yield DeleteRequest(target=volta)
        return

    pieces: list[Piece] = [Piece(start=layout.start.position, end=layout.body_end.position)]
    previous = layout.body_end.position
    for fragment in layout.fragments:
        pieces.append(Piece(start=previous, end=fragment.end.position))
        previous = fragment.end.position

    try:
        check_nesting(
            elements=[
                *pieces_of_elements(geometry=geometry, contexts=contexts, without=volta),
                pieces,
            ]
        )
    except ValueError as error:
        raise MutationRejectedError(str(error)) from error

    start: TemporalAnchor | None = yield from _anchor_of(ref=layout.start.ref)
    body_end: TemporalAnchor | None = yield from _anchor_of(ref=layout.body_end.ref)
    if start is None or body_end is None:
        raise MutationRejectedError("The body of a volta lies between barlines.")

    fragments: list[NewFragment] = []
    for fragment in layout.fragments:
        end: TemporalAnchor | None = yield from _anchor_of(ref=fragment.end.ref)
        fragments.append(NewFragment(end=end, passes=fragment.passes))

    yield ReshapeVoltaAction(
        target=volta, start=start, body_end=body_end, fragments=tuple(fragments)
    )
