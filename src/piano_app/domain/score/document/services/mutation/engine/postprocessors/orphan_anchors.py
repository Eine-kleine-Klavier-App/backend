from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from .base import MutatedStatePostprocessor


class OrphanAnchorsPostprocessor(MutatedStatePostprocessor):
    """Removes every anchor nothing starts at, ends at or is held by any more.

    Runs last: the fill reuses an anchor a removal left behind before it is judged.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[DeleteRequest]:
        return [
            DeleteRequest(target=anchor)
            for measure in document.measures
            for anchor in measure.anchors
            if anchor.is_orphan
        ]
