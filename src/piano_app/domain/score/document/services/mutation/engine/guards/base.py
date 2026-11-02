from collections.abc import Sequence
from typing import Protocol

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest


class InvariantGuard(Protocol):
    """Guards are intended to keep invariants no analyzer has to remember: the engine asks
    them for fixes once, at the end of a pass after the postprocessors, against the live
    document.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[MutationRequest]: ...
