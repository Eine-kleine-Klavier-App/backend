from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    MutatedStatePostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    DeleteNoteCarrierRequest,
    DeleteRestCarrierRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteLeafRequest,
    DeleteRhythmicGroupRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    DeleteTemporalAnchorRequest,
)


class CleanupPostprocessor(MutatedStatePostprocessor):
    """Removes childless scaffolding left by deletions — empty carriers, carrier-less
    leaves, groups without children and orphan anchors. A group holding only rests is
    valid and stays. One level per pass; the fixpoint unwinds carrier → leaf → group →
    anchor.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
    ) -> Sequence[MutationRequest]:
        cleanup_requests: list[MutationRequest] = []

        for measure in document.measures:
            for anchor in measure.anchors:
                if anchor.is_orphan:
                    cleanup_requests.append(DeleteTemporalAnchorRequest(target=anchor))
                    continue

                for container in anchor.containers:
                    if isinstance(container, GroupRhythmicContainer):
                        if not container.children:
                            cleanup_requests.append(DeleteRhythmicGroupRequest(target=container))
                        continue

                    if not isinstance(container, LeafRhythmicContainer):
                        raise ValueError(f"Unknown container type: {type(container)}")

                    carrier = container.carrier
                    if carrier is None:
                        cleanup_requests.append(DeleteLeafRequest(target=container))
                        continue

                    if isinstance(carrier, NoteCarrier) and not carrier.notes:
                        cleanup_requests.append(DeleteNoteCarrierRequest(target=carrier))
                    elif isinstance(carrier, RestCarrier) and carrier.rest is None:
                        cleanup_requests.append(DeleteRestCarrierRequest(target=carrier))

        return cleanup_requests
