from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from .base import MutatedStatePostprocessor
from .content import holds_content


class EmptyLeavesPostprocessor(MutatedStatePostprocessor):
    """Removes every leaf left without a note or a rest — no carrier, an empty note
    carrier or a rest carrier without its rest — in one go; each leaf's own cascade takes
    its carrier with it.

    All of them go before anything is filled, so the hole a deletion leaves is one gap
    however its entities were named. Grace groups have no deletion cascade yet.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[DeleteRequest]:
        return [
            DeleteRequest(target=leaf)
            for voice in document.voices
            for leaf in iter_leaves(voice)
            if not holds_content(container=leaf)
        ]
