from piano_app.domain.score.document.models.context import SustainHold
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
    CreateSustainHoldAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateSustainHoldRequest,
)


class CreateSustainHoldAnalyzer:
    """Decides placement for a new sustain hold. Both ends are reused or created.

    It must end after it starts and may not overlap another sustain hold; both are refused
    before anything is created. A hold may end where the next one starts: that is a change of
    pedal.
    """

    def analyze(
        self,
        *,
        request: CreateSustainHoldRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        start = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        end = global_position(
            geometry=geometry, measure=request.end_measure, position=request.end_position
        )
        if end <= start:
            raise MutationRejectedError("A sustain hold must end after it starts.")

        refuse_clashes(
            clashes=find_clashes(
                contexts=contexts,
                kind=SustainHold,
                start=start,
                end=end,
                staff=None,
                voice=None,
            )
        )

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.end_measure, position=request.end_position
        )
        yield CreateSustainHoldAction(start=start_anchor, end=end_anchor)
