from piano_app.domain.score.document.models.context import DynamicChange
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
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateDynamicChangeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateDynamicChangeRequest,
)


class CreateDynamicChangeAnalyzer:
    """Decides placement and displacement for a new dynamic change.

    The anchor is reused or created. A dynamic of its voice already starting at that anchor is
    displaced. A dynamic may sit at the start or the end of a hairpin of its voice but not
    strictly inside one, refused otherwise before anything is created.
    """

    def analyze(
        self,
        *,
        request: CreateDynamicChangeRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=DynamicChange,
            start=global_position(
                geometry=geometry, measure=request.measure, position=request.position
            ),
            end=None,
            staff=None,
            voice=request.voice,
        )
        refuse_clashes(clashes=clashes)
        yield from displace_same_place(clashes=clashes)

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield CreateDynamicChangeAction(start=anchor, voice=request.voice, dynamic=request.dynamic)
