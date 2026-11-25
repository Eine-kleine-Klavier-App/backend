from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.contexts import global_position
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateSlurAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateSlurRequest,
)


class CreateSlurAnalyzer:
    """Decides placement for a new slur. Both ends are reused or created.

    It must end after it starts. Slurs may overlap and nest, so nothing else is checked.
    """

    def analyze(
        self,
        *,
        request: CreateSlurRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        start = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        end = global_position(
            geometry=geometry, measure=request.end_measure, position=request.end_position
        )
        if end <= start:
            raise MutationRejectedError("A slur must end after it starts.")

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.end_measure, position=request.end_position
        )
        yield CreateSlurAction(start=start_anchor, end=end_anchor, voice=request.voice)
