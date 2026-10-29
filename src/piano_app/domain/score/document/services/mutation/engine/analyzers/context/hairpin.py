from piano_app.domain.score.document.models.context import Hairpin
from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice
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
    refuse_clashes,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateHairpinAction,
    UpdateHairpinStepsAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateHairpinRequest,
    UpdateHairpinStepsRequest,
)


class CreateHairpinAnalyzer:
    """Decides placement for a new hairpin. Both ends are reused or created.

    It must end after it starts, may not overlap another hairpin that shares a voice and may
    not hold a dynamic of its voices strictly inside; all refused before anything is created.
    """

    def analyze(
        self,
        *,
        request: CreateHairpinRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        voices: tuple[Voice, ...] = request.voices
        if not voices or len(voices) != len(set(voices)):
            raise MutationRejectedError("A hairpin names at least one voice, each once.")

        if request.steps == 0:
            raise MutationRejectedError("A hairpin must change the dynamic by at least one level.")

        start = global_position(
            geometry=geometry, measure=request.start_measure, position=request.start_position
        )
        end = global_position(
            geometry=geometry, measure=request.end_measure, position=request.end_position
        )
        if end <= start:
            raise MutationRejectedError("A hairpin must end after it starts.")

        refuse_clashes(
            clashes=find_clashes(
                contexts=contexts,
                kind=Hairpin,
                start=start,
                end=end,
                staff=None,
                voices=voices,
            )
        )

        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )
        end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.end_measure, position=request.end_position
        )
        yield CreateHairpinAction(
            start=start_anchor, end=end_anchor, voices=voices, steps=request.steps
        )


class UpdateHairpinStepsAnalyzer:
    """Changes by how many dynamic levels a hairpin moves; the hairpin itself stays."""

    def analyze(
        self,
        *,
        request: UpdateHairpinStepsRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        if request.steps == 0:
            raise MutationRejectedError("A hairpin must change the dynamic by at least one level.")

        yield UpdateHairpinStepsAction(target=request.target, steps=request.steps)
