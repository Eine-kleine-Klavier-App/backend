from piano_app.domain.score.document.models.context import ClefChange
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
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateClefChangeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)


class CreateClefChangeAnalyzer:
    """Decides placement and displacement for a new clef change.

    The anchor is reused or created, exactly like a metric leaf. A clef change
    already asserted on the same staff at that anchor is replaced, not rejected —
    "set a new clef here" reads as a replacement, not an error, the same way
    inserting a note into an occupied slot does.
    """

    def analyze(
        self,
        *,
        request: CreateClefChangeRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        yield from displace_same_place(
            clashes=find_clashes(
                contexts=contexts,
                kind=ClefChange,
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

        yield CreateClefChangeAction(
            start=anchor,
            staff=request.staff,
            clef=request.clef,
            octave_transposition=request.octave_transposition,
        )
