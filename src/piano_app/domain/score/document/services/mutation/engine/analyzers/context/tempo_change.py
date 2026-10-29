from piano_app.domain.score.document.models.context import TempoChange
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.contexts import (
    Clash,
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
    refuse_clashes,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateTempoChangeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateTempoChangeRequest,
)


class CreateTempoChangeAnalyzer:
    """Decides placement and displacement for a new tempo change.

    The anchor is reused or created. A tempo change already starting at that anchor is
    replaced, not rejected — "set a new tempo here" reads as a replacement. A tempo may sit at
    the start or the end of a tempo transition but not strictly inside one, refused otherwise
    before anything is created.
    """

    def analyze(
        self,
        *,
        request: CreateTempoChangeRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        if request.bpm < 1:
            raise MutationRejectedError("Tempo must be at least 1 beat per minute.")

        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=TempoChange,
            start=global_position(
                geometry=geometry, measure=request.measure, position=request.position
            ),
            end=None,
            staff=None,
            voices=None,
        )
        refuse_clashes(clashes=clashes)
        yield from displace_same_place(clashes=clashes, voices=None)

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield CreateTempoChangeAction(
            start=anchor,
            beat=request.beat,
            bpm=request.bpm,
            show_label=request.show_label,
        )
