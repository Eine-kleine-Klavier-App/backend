from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import SpanContext
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import MEASURE_START, Measure
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    split_crossing_groups,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    KeepContextEndsRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    ChangeTimeSignatureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CutAtBarlinesRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    RebarMeasuresRequest,
)


class ChangeTimeSignatureAnalyzer:
    """Gives exactly the selected measures a new time signature (time-signature-change).

    Decides nothing itself: it checks the selection and yields the axis requests in order,
    each analysed on what the ones before it left —
    1. frames: when the selection's length changes, every group crossing the barline after
       its last measure is split there, so nothing crosses the end that moves; its start
       never moves and is never split, nor is an end that stays where it was. Then the
       selection is rebarred — its measures take the signature, everything in them keeps
       its time from the selection's start, and it becomes as many measures as its total
       length needs, added or removed at its end;
    2. spans: every leaf of the selection now crossing a barline is cut there;
    3. contexts: a span context ending on the selection's end barline keeps that end at the
       selection's old length from its start, inside the selection once it grew.
    Measures outside keep their signature, and everything after the selection its measure
    and beat.

    Before its first yield it only reads what the edit may change: which span contexts end
    on its end barline — carried across as entities, judged by their own request. After the
    rebar the selection is read from the live chain: from its first measure up to the one
    that followed its last.

    The selection must be contiguous, refused otherwise; a measure listed twice counts once.
    When every selected measure already has the signature nothing changes.
    """

    def analyze(
        self,
        *,
        request: ChangeTimeSignatureRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        document: ScoreDocument = request.document
        time_signature: RhythmicSize = request.time_signature

        if not request.measures:
            raise MutationRejectedError("A time signature is changed on at least one measure.")

        if any(measure not in document.measures for measure in request.measures):
            raise MutationRejectedError("The selected measures must be in the document.")

        selected: list[Measure] = [
            measure for measure in document.measures if measure in request.measures
        ]
        first_index: int = document.measures.index(selected[0])
        if document.measures[first_index : first_index + len(selected)] != selected:
            raise MutationRejectedError("The selected measures must be contiguous.")

        if all(measure.time_signature == time_signature for measure in selected):
            return

        first: Measure = selected[0]
        last: Measure = selected[-1]
        after: Measure | None = last.next_measure
        old_length: Fraction = sum(
            (measure.time_signature.fraction for measure in selected),
            Fraction(0),
        )

        # the span contexts ending on the selection's end barline
        ending: list[SpanContext] = []
        if after is not None:
            for anchor in after.anchors:
                if anchor.position == MEASURE_START:
                    ending.extend(anchor.ending_contexts)

        # the end edge moves only when the new measures do not divide the old length: only
        # then does something come between what crosses it, so only then is it split
        if after is not None and old_length % time_signature.fraction != 0:
            yield from split_crossing_groups(measure=after, geometry=geometry)

        yield RebarMeasuresRequest(
            document=document,
            measures=tuple(selected),
            time_signature=time_signature,
        )

        rebarred: list[Measure] = []
        measure: Measure | None = first
        while measure is not None and measure is not after:
            rebarred.append(measure)
            measure = measure.next_measure

        yield CutAtBarlinesRequest(measures=tuple(rebarred))

        if ending:
            yield KeepContextEndsRequest(
                contexts=tuple(ending),
                measures=tuple(rebarred),
                offset=old_length,
            )
