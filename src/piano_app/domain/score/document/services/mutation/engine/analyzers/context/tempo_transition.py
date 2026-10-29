from piano_app.domain.score.document.models.context import TempoTransition
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.contexts import (
    ContextIndex,
    find_clashes,
    global_position,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.context.clashes import (
    refuse_clashes,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateTempoTransitionAction,
    UpdateTempoTransitionRatioAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateTempoTransitionRequest,
    UpdateTempoTransitionRatioRequest,
)


class CreateTempoTransitionAnalyzer:
    """Decides placement for a new tempo transition. Both ends are reused or created.

    It must end after it starts, may not overlap another tempo transition and may not hold a
    tempo change strictly inside; all refused before anything is created.
    """

    def analyze(
        self,
        *,
        request: CreateTempoTransitionRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        if request.ratio <= 0 or request.ratio == 1:
            raise MutationRejectedError("A tempo transition's ratio is positive and not one.")

        start = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        end = global_position(
            geometry=geometry, measure=request.end_measure, position=request.end_position
        )
        if end <= start:
            raise MutationRejectedError("A tempo transition must end after it starts.")

        refuse_clashes(
            clashes=find_clashes(
                contexts=contexts,
                kind=TempoTransition,
                start=start,
                end=end,
                staff=None,
                voices=None,
            )
        )

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.end_measure, position=request.end_position
        )
        yield CreateTempoTransitionAction(start=start_anchor, end=end_anchor, ratio=request.ratio)


class UpdateTempoTransitionRatioAnalyzer:
    """Changes the ratio of speed a tempo transition ends at; the transition itself stays."""

    def analyze(
        self,
        *,
        request: UpdateTempoTransitionRatioRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        if request.ratio <= 0 or request.ratio == 1:
            raise MutationRejectedError("A tempo transition's ratio is positive and not one.")

        yield UpdateTempoTransitionRatioAction(target=request.target, ratio=request.ratio)
