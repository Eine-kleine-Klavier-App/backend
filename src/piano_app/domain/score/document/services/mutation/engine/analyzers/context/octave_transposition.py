from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.contexts import ContextIndex, find_clashes
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.context.clashes import (
    refuse_clashes,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateOctaveTranspositionAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateOctaveTranspositionRequest,
)


class CreateOctaveTranspositionAnalyzer:
    """Decides placement for a new octave transposition span.

    Both ends are reused or created, exactly like a point context's single anchor.
    Unlike a point context, a conflict here is any overlap with an existing octave
    transposition on the same staff, not just a shared anchor — and there is no
    single well-defined replacement for two overlapping brackets, so a conflict is
    rejected outright rather than displaced. Touching (but not overlapping) spans
    are never a conflict.
    """

    def analyze(
        self,
        *,
        request: CreateOctaveTranspositionRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        start_point: Point = Point(
            frame=geometry.of_measure(measure=request.start_measure),
            value=request.start_position.value,
        ).to(frame=geometry.root)
        end_point: Point = Point(
            frame=geometry.of_measure(measure=request.end_measure),
            value=request.end_position.value,
        ).to(frame=geometry.root)

        if end_point.value <= start_point.value:
            raise MutationRejectedError("Octave transposition must end after it starts.")

        refuse_clashes(
            clashes=find_clashes(
                contexts=contexts,
                kind=OctaveTransposition,
                start=start_point.value,
                end=end_point.value,
                staff=request.staff,
                voices=None,
            )
        )

        # the overlap is settled above; nothing geometric is read past the first yield
        start_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.start_measure, position=request.start_position
        )

        end_anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.end_measure, position=request.end_position
        )

        yield CreateOctaveTranspositionAction(
            start=start_anchor,
            end=end_anchor,
            staff=request.staff,
            octaves=request.octaves,
        )
