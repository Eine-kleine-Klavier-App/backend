from piano_app.domain.score.document.models.context import (
    KEY_SIGNATURE_ACCIDENTALS,
    KEY_SIGNATURE_STEPS,
    KeySignatureChange,
)
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
    displace_same_place,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateKeySignatureChangeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateKeySignatureChangeRequest,
)


class CreateKeySignatureChangeAnalyzer:
    """Decides placement and displacement for a new key signature change.

    Same shape as ``CreateClefChangeAnalyzer`` — the anchor is reused or created,
    and a key signature already asserted on the same staff at that anchor is
    replaced, not rejected.
    """

    def analyze(
        self,
        *,
        request: CreateKeySignatureChangeRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        if len(request.alterations) != KEY_SIGNATURE_STEPS:
            raise MutationRejectedError(
                f"A key signature gives {KEY_SIGNATURE_STEPS} alterations, one for each step."
            )

        for alteration in request.alterations:
            if alteration not in KEY_SIGNATURE_ACCIDENTALS:
                raise MutationRejectedError("A key signature has no double accidentals.")

        yield from displace_same_place(
            clashes=find_clashes(
                contexts=contexts,
                kind=KeySignatureChange,
                start=global_position(
                    geometry=geometry, measure=request.measure, position=request.position
                ),
                end=None,
                staff=request.staff,
                voices=None,
            ),
            voices=None,
        )

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield CreateKeySignatureChangeAction(
            start=anchor,
            staff=request.staff,
            alterations=request.alterations,
        )
