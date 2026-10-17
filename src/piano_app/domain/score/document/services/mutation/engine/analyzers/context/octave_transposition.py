from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.geometry import Point, Span, meetings
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import (
    Bound,
    MutationRejectedError,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateOctaveTranspositionAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateOctaveTranspositionRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
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
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)

        geometry: ScoreGeometry = ScoreGeometry(origin=request.start_measure)
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

        new_span: Span = Span.between(start=start_point, end=end_point)

        existing: list[tuple[OctaveTransposition, Span]] = [
            (
                context,
                Span.between(
                    start=geometry.point_of(anchor=context.start),
                    end=geometry.point_of(anchor=context.end),
                ),
            )
            for context in request.staff.contexts
            if isinstance(context, OctaveTransposition)
        ]
        if meetings(span=new_span, candidates=existing):
            raise MutationRejectedError(
                "Octave transposition overlaps an existing one on this staff."
            )

        start_anchor: Bound[TemporalAnchor] = self._anchor_ref(
            buffer=buffer,
            measure=request.start_measure,
            position=request.start_position,
        )
        end_anchor: Bound[TemporalAnchor] = self._anchor_ref(
            buffer=buffer,
            measure=request.end_measure,
            position=request.end_position,
        )

        buffer.incorporate(
            item=CreateOctaveTranspositionAction(
                start=start_anchor,
                end=end_anchor,
                staff=request.staff,
                octaves=request.octaves,
                out=request.out,
            ),
        )

        return buffer

    @staticmethod
    def _anchor_ref(
        *,
        buffer: EmitBuffer,
        measure: Measure,
        position: MeasurePosition,
    ) -> Bound[TemporalAnchor]:
        existing_anchor: TemporalAnchor | None = find_anchor_at(
            measure=measure,
            position=position,
        )
        if existing_anchor is not None:
            return existing_anchor

        anchor_ref: ResultRef[TemporalAnchor] = ResultRef[TemporalAnchor]()
        buffer.incorporate(
            item=CreateTemporalAnchorRequest(measure=measure, position=position, out=anchor_ref),
        )
        return anchor_ref
