from fractions import Fraction

from piano_app.domain.score.document.models.context import SpanContext
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    MeasurePosition,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    KeepContextEndsRequest,
    UpdateContextEndRequest,
)


class KeepContextEndsAnalyzer:
    """Keeps span contexts ending at a fixed time from the start of a run of measures
    (time-signature-change: an end on the selection's end barline keeps its time from the
    selection's start).

    The place is found in the measures as they are now: the measure and position the offset
    falls in, or the start of the measure after them when it is their whole length. An end
    already there stays; any other moves there, found or created by the move, and the
    context itself is kept. Decided before the first yield, in model terms.
    """

    def analyze(
        self,
        *,
        request: KeepContextEndsRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        offset: Fraction = request.offset

        target: Measure | None = None
        position: MeasurePosition = MEASURE_START
        start: Fraction = Fraction(0)
        for measure in request.measures:
            length: Fraction = measure.time_signature.fraction
            if offset < start + length:
                target = measure
                position = MeasurePosition.of_fraction(fraction=offset - start)
                break

            start += length

        if target is None:
            if offset != start:
                raise ValueError("A kept context end lies past the measures it is kept in.")

            target = request.measures[-1].next_measure

        if target is None:
            raise ValueError("A context end at the end of the score has no anchor to keep.")

        moved: list[SpanContext] = [
            context
            for context in request.contexts
            if context.end is not None
            and (context.end.measure is not target or context.end.position != position)
        ]

        for context in moved:
            yield UpdateContextEndRequest(target=context, measure=target, position=position)
