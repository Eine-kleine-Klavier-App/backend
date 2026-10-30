from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateRestAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateRestRequest,
)


class CreateRestAnalyzer:
    """Creates a rest in the rest carrier its request names; where that carrier comes
    from is decided above, by the spans."""

    def analyze(
        self,
        *,
        request: CreateRestRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield CreateRestAction(
            rest_carrier=request.carrier,
            staff=request.staff,
        )
