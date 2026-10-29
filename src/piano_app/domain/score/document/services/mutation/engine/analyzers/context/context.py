from piano_app.domain.score.document.models.context import (
    Context,
    SpanContext,
    StaffScoped,
    VoicesScoped,
)
from piano_app.domain.score.document.models.structural import MEASURE_START, TemporalAnchor
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
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    UpdateContextEndAction,
    UpdateContextStartAction,
    UpdateContextVoicesAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CloseOpenContextEndsRequest,
    OpenContextEndRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
    UpdateContextVoicesRequest,
)


class UpdateContextStartAnalyzer:
    """Moves a context's start to a found or new anchor; the context itself stays.

    A span context's start must stay before its end, refused otherwise — checked on the
    measure and position before the anchor is found, so a refusal creates nothing.
    """

    def analyze(
        self,
        *,
        request: UpdateContextStartRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        context: Context = request.target

        if not request.measure.holds(position=request.position):
            raise MutationRejectedError("Position lies at or past the end of the measure.")

        if (
            isinstance(context, SpanContext)
            and context.end is not None
            and context.end.precedes_or_equals_position(
                measure=request.measure,
                position=request.position,
            )
        ):
            raise MutationRejectedError("A span context's start must stay before its end.")

        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=type(context),
            start=global_position(
                geometry=geometry, measure=request.measure, position=request.position
            ),
            end=geometry.end_of(context=context).value
            if isinstance(context, SpanContext)
            else None,
            staff=context.staff if isinstance(context, StaffScoped) else None,
            voices=context.voices if isinstance(context, VoicesScoped) else None,
            ignore=context,
        )
        if clashes:
            raise MutationRejectedError(clashes[0].reason)

        start: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield UpdateContextStartAction(target=context, start=start)


class UpdateContextEndAnalyzer:
    """Moves a span context's end to a found or new anchor; the context itself stays.

    Its end must stay after its start, refused otherwise — checked on the measure and
    position before the anchor is found, so a refusal creates nothing.
    """

    def analyze(
        self,
        *,
        request: UpdateContextEndRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        context: SpanContext = request.target

        if not request.measure.holds(position=request.position):
            raise MutationRejectedError("Position lies at or past the end of the measure.")

        is_after_start: bool = context.start.precedes_or_equals_position(
            measure=request.measure,
            position=request.position,
        ) and not (
            context.start.measure is request.measure and context.start.position == request.position
        )
        if not is_after_start:
            raise MutationRejectedError("A span context's end must stay after its start.")

        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=type(context),
            start=geometry.point_of(anchor=context.start).value,
            end=global_position(
                geometry=geometry, measure=request.measure, position=request.position
            ),
            staff=context.staff if isinstance(context, StaffScoped) else None,
            voices=context.voices if isinstance(context, VoicesScoped) else None,
            ignore=context,
        )
        if clashes:
            raise MutationRejectedError(clashes[0].reason)

        end: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield UpdateContextEndAction(target=context, end=end)


class OpenContextEndAnalyzer:
    """Makes a span context last until the end of the score; the context itself stays.

    Refused when it already does, or when a context of its kind that it may not share the
    timeline with lies in the stretch it then covers.
    """

    def analyze(
        self,
        *,
        request: OpenContextEndRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        context: SpanContext = request.target
        if context.end is None:
            raise MutationRejectedError(
                "The span context already lasts until the end of the score."
            )

        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=type(context),
            start=geometry.point_of(anchor=context.start).value,
            end=geometry.root.extent,
            staff=context.staff if isinstance(context, StaffScoped) else None,
            voices=context.voices if isinstance(context, VoicesScoped) else None,
            ignore=context,
        )
        if clashes:
            raise MutationRejectedError(clashes[0].reason)

        yield UpdateContextEndAction(target=context, end=None)


class CloseOpenContextEndsAnalyzer:
    """Anchors every span that lasts until the end of the score at the start of the last
    measure, right after a measure was added after the one that used to be last, so that those
    spans end where they did. Each is moved by an ordinary end move, which finds or creates the
    anchor."""

    def analyze(
        self,
        *,
        request: CloseOpenContextEndsRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        open_spans: list[SpanContext] = [
            context
            for context in contexts.contexts()
            if isinstance(context, SpanContext) and context.end is None
        ]
        for context in open_spans:
            yield UpdateContextEndRequest(
                target=context, measure=request.document.measures[-1], position=MEASURE_START
            )


class UpdateContextVoicesAnalyzer:
    """Changes the voices a context applies to; the context itself stays, so at least one
    voice must remain — a context left with none is deleted instead."""

    def analyze(
        self,
        *,
        request: UpdateContextVoicesRequest,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis:
        if not request.voices:
            raise MutationRejectedError("A context keeps at least one voice.")

        context: VoicesScoped = request.target
        clashes: list[Clash] = find_clashes(
            contexts=contexts,
            kind=type(context),
            start=geometry.point_of(anchor=context.start).value,
            end=geometry.end_of(context=context).value
            if isinstance(context, SpanContext)
            else None,
            staff=context.staff if isinstance(context, StaffScoped) else None,
            voices=request.voices,
            ignore=context,
        )
        if clashes:
            raise MutationRejectedError(clashes[0].reason)

        yield UpdateContextVoicesAction(target=context, voices=request.voices)
