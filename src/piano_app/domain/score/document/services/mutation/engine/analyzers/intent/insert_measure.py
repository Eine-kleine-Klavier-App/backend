from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    KeySignatureChange,
    Refrain,
    TempoChange,
    Volta,
)
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at, neighbour_signature
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    split_crossing_groups,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    MoveRefrainEndRequest,
    MoveVoltaBoundaryRequest,
    UpdateContextStartRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    InsertMeasureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
)


class InsertMeasureAnalyzer:
    """Adds a measure before a given one (measure-operations).

    Before the first measure the clef, key signature, tempo and dynamic starting at its start
    are moved to the start of the new measure, so the score keeps them at its start and the
    notes already there keep their sound (initial-clef-invariant). A repeat, or the last ending
    of a volta, that ends where the measure starts is moved to end at the start of the new
    measure, so a measure added after a repeat stays outside it. Any other context stays
    where it is. The contexts are read before the first yield and carried across as
    entities; the new measure is what its create request sends back.
    """

    def analyze(
        self,
        *,
        request: InsertMeasureRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        before: Measure = request.before

        carried: list[ClefChange | KeySignatureChange | TempoChange | DynamicChange] = []
        if before.prev_measure is None:
            start: TemporalAnchor | None = find_anchor_at(measure=before, position=MEASURE_START)
            if start is not None:
                for context in start.starting_contexts:
                    if isinstance(
                        context, ClefChange | KeySignatureChange | TempoChange | DynamicChange
                    ):
                        carried.append(context)

        # the repeats and voltas that end where the measure starts: their ends stay outside
        # the new measure
        start_here: TemporalAnchor | None = find_anchor_at(measure=before, position=MEASURE_START)
        refrains_ending: list[Refrain] = []
        voltas_ending: list[Volta] = []
        if start_here is not None:
            index: ContextIndex = ContextIndex(document=request.document, geometry=geometry)
            refrains_ending = [
                refrain
                for refrain in index.contexts_of(kind=Refrain, scope=Scope.score())
                if refrain.end is start_here
            ]
            voltas_ending = [
                volta
                for volta in index.contexts_of(kind=Volta, scope=Scope.score())
                if volta.fragments[-1].end is start_here
            ]

        yield from split_crossing_groups(measure=before, geometry=geometry)

        inserted: Measure = expect_sent(
            sent=(
                yield CreateEmptyMeasureRequest(
                    document=request.document,
                    before=before,
                    time_signature=neighbour_signature(document=request.document, before=before),
                )
            ),
            expected=Measure,
        )

        for context in carried:
            yield UpdateContextStartRequest(
                target=context,
                measure=inserted,
                position=MEASURE_START,
            )

        for refrain in refrains_ending:
            yield MoveRefrainEndRequest(target=refrain, measure=inserted, position=MEASURE_START)

        for volta in voltas_ending:
            yield MoveVoltaBoundaryRequest(
                target=volta,
                boundary=len(volta.fragments),
                measure=inserted,
                position=MEASURE_START,
            )
