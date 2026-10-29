from fractions import Fraction

from piano_app.domain.score.document.models.context import (
    Context,
    Refrain,
    SpanContext,
    VoicesScoped,
    Volta,
)
from piano_app.domain.score.document.models.structural import MEASURE_START, Measure, Voice
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    ClearContextsRequest,
    CollapseRefrainRequest,
    CollapseVoltaRequest,
    OpenContextEndRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
    UpdateContextVoicesRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


class ClearContextsAnalyzer:
    """Clears every context out of a measure about to be removed, keeping the effect of
    each on what is left of its region (measure-operations, by region).

    A context placed in the measure whose region continues after it moves to the start of
    the remaining region — the start of the following measure, where the measure's boundary
    falls once it is gone; the boundary anchor is found or created by the move. When
    nothing of its region remains — the next context of the same kind already starts
    there, or the measure is the last one — it is removed; a context already at the
    destination is never replaced. A voices-scoped point context is read voice by voice: it
    keeps only the voices it still governs past the measure, and goes when none is left. A
    span context whose end lay in the measure has its region cut: the end moves left to the
    boundary, or, when the measure is the last one, it lasts until the end of the score. The
    context itself is kept whenever it moves.

    The regions are read before the first yield; only contexts and the boundary measure are
    carried across. A repeat or a volta with a boundary in the measure has the boundaries
    drawn together to where the measure ends, and goes when nothing of it is left.
    """

    def analyze(
        self,
        *,
        request: ClearContextsRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        measure: Measure = request.measure
        boundary: Measure | None = measure.next_measure

        measure_end: Fraction = geometry.measure_span(measure=measure).end

        # a span context starting and ending inside the measure is seen twice
        touched: list[Context] = []
        for anchor in measure.anchors:
            for context in [*anchor.starting_contexts, *anchor.ending_contexts]:
                # a refrain and a volta are held by their jumps: they are drawn together below
                if isinstance(context, Refrain | Volta):
                    continue

                if not any(context is listed for listed in touched):
                    touched.append(context)

        # the repeats and voltas with a boundary in the measure; read before the first yield
        refrains: list[Refrain] = [
            refrain
            for refrain in contexts.contexts_of(kind=Refrain, scope=Scope.score())
            if any(
                anchor is not None and anchor.measure is measure
                for anchor in (refrain.start, refrain.end)
            )
        ]
        voltas: list[Volta] = [
            volta
            for volta in contexts.contexts_of(kind=Volta, scope=Scope.score())
            if any(
                anchor is not None and anchor.measure is measure
                for anchor in (
                    volta.start,
                    volta.body_end,
                    *(fragment.end for fragment in volta.fragments),
                )
            )
        ]

        doomed: list[Context] = []
        moved_starts: list[tuple[Context, Measure]] = []
        trimmed: list[tuple[VoicesScoped, tuple[Voice, ...]]] = []
        moved_ends: list[tuple[SpanContext, Measure]] = []
        opened_ends: list[SpanContext] = []
        for context in touched:
            if context.start.measure is measure:
                if isinstance(context, VoicesScoped) and not isinstance(context, SpanContext):
                    # read voice by voice: kept for the voices it still governs past the measure
                    governed: list[Voice] = contexts.governed_voices(
                        context=context, at=measure_end
                    )
                    if boundary is not None and governed:
                        moved_starts.append((context, boundary))
                        if len(governed) < len(context.voices):
                            trimmed.append((context, tuple(governed)))
                    else:
                        doomed.append(context)

                else:
                    # placed in the measure: kept only when its region reaches past it
                    region: Span = contexts.region_of(context=context)
                    if boundary is not None and region.end > measure_end:
                        moved_starts.append((context, boundary))
                    else:
                        doomed.append(context)

            elif isinstance(context, SpanContext):
                # its start lies before the measure; its end moves left to the boundary after it,
                # or, when the measure is the last one, the span lasts until the end of what is left
                if boundary is not None:
                    moved_ends.append((context, boundary))
                else:
                    opened_ends.append(context)

            else:
                doomed.append(context)

        for context in doomed:
            yield DeleteRequest(target=context)

        for voices_context, voices in trimmed:
            yield UpdateContextVoicesRequest(target=voices_context, voices=voices)

        # spans first: a tempo or dynamic moved to the boundary must not meet a gradual change
        # of its kind that has not moved there yet
        for context, start_measure in sorted(
            moved_starts, key=lambda moved: not isinstance(moved[0], SpanContext)
        ):
            yield UpdateContextStartRequest(
                target=context,
                measure=start_measure,
                position=MEASURE_START,
            )

        for span_context, end_measure in moved_ends:
            yield UpdateContextEndRequest(
                target=span_context,
                measure=end_measure,
                position=MEASURE_START,
            )

        for span_context in opened_ends:
            yield OpenContextEndRequest(target=span_context)

        for refrain in refrains:
            yield CollapseRefrainRequest(target=refrain, measure=measure)

        for volta in voltas:
            yield CollapseVoltaRequest(target=volta, measure=measure)
