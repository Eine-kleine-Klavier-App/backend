from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from math import ceil, floor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
    DeleteEmptyMeasureRequest,
    RebarMeasuresRequest,
    UpdateMeasureTimeSignatureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    UpdateTemporalAnchorRequest,
)

# a place in the selection: the index of its measure and the position inside it
type _Place = tuple[int, MeasurePosition]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Move:
    """One anchor's move, in model terms only: the place it leaves and the one it takes."""

    anchor: TemporalAnchor
    source: _Place
    target: _Place


class RebarMeasuresAnalyzer:
    """Gives the selected measures a new time signature and moves their barlines
    (time-signature-change).

    Every anchor of the selection keeps its time from the selection's start and moves to
    the measure and position that time falls in under the new signature, with everything
    starting or ending at it — containers of every voice, contexts — so all of it keeps its
    identity; nothing is taken off and placed again. The number of measures follows the
    selection's total length, not its content: it becomes total / new length measures,
    rounded up, so everything in it fits and no measure is dropped for being empty. The
    selected measures are kept from the first; the missing ones are added after the last,
    empty and of the new signature, and the ones beyond the new count are removed once
    their anchors moved out. Nothing may cross the selection's end when it moves: what did
    was split before; nothing outside is touched.

    Ordered so no measure ever holds an anchor at or past its end and the anchors keep their
    order on the timeline after every step: the added measures first, then the kept
    measures that do not shrink take the new signature, the anchors moving later move from
    the last one back, those moving earlier from the first one on, the kept measures that
    shrink take the signature once their anchors lie inside it, and the emptied measures
    go. Between the first and the last move the timeline is not read.

    Everything is decided before the first yield, in measure indexes and positions; only
    measures and anchors are carried across.
    """

    def analyze(
        self,
        *,
        request: RebarMeasuresRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        document: ScoreDocument = request.document
        measures: list[Measure] = list(request.measures)
        time_signature: RhythmicSize = request.time_signature
        length: Fraction = time_signature.fraction

        if not measures:
            raise ValueError("A rebar needs at least one measure.")

        for earlier, later in pairwise(measures):
            if earlier.next_measure is not later:
                raise ValueError("The rebarred measures must be contiguous, in score order.")

        after: Measure | None = measures[-1].next_measure
        start: Fraction = geometry.measure_span(measure=measures[0]).start
        old_length: Fraction = sum(
            (measure.time_signature.fraction for measure in measures),
            Fraction(0),
        )

        # every anchor with its place and its time from the selection's start, and how far
        # the containers starting there reach — never past the selection's end
        placed: list[tuple[TemporalAnchor, int, Fraction]] = []
        content_end: Fraction = Fraction(0)
        for index, measure in enumerate(measures):
            for anchor in measure.anchors:
                placed.append((anchor, index, geometry.point_of(anchor=anchor).value - start))

                for container in anchor.containers:
                    end: Fraction = geometry.global_span_of(container=container).end - start
                    content_end = max(content_end, end)

        # an end that stays where it was may be crossed: nothing comes between the two sides
        if content_end > old_length and old_length % length != 0:
            raise ValueError(
                "A container crosses the end of the rebarred measures, which moves: it must be "
                "split there first."
            )

        # every anchor lies before the old end, every container ends by it or by an end
        # that stays: both fit
        count: int = ceil(old_length / length)

        moves: list[_Move] = []
        for anchor, index, offset in placed:
            target_index: int = floor(offset / length)
            target: _Place = (
                target_index,
                MeasurePosition.of_fraction(fraction=offset - target_index * length),
            )
            source: _Place = (index, anchor.position)
            if target != source:
                moves.append(_Move(anchor=anchor, source=source, target=target))

        # the order on the timeline holds after every single move: the anchors moving later
        # go from the last, then those moving earlier from the first, so none passes another
        # and each place is free when taken
        ordered: list[_Move] = [
            *reversed([move for move in moves if move.source < move.target]),
            *[move for move in moves if move.target < move.source],
        ]

        kept: list[Measure] = measures[:count]
        removed: list[Measure] = measures[count:]
        growing: list[Measure] = [
            measure
            for measure in kept
            if measure.time_signature != time_signature
            and measure.time_signature.fraction <= length
        ]
        shrinking: list[Measure] = [
            measure for measure in kept if measure.time_signature.fraction > length
        ]

        # the measure of each index a move takes: the kept ones, then the added ones
        targets: list[Measure] = list(kept)
        for _ in range(count - len(measures)):
            added: Measure = expect_sent(
                sent=(
                    yield CreateEmptyMeasureRequest(
                        document=document,
                        before=after,
                        time_signature=time_signature,
                    )
                ),
                expected=Measure,
            )
            targets.append(added)

        for measure in growing:
            yield UpdateMeasureTimeSignatureRequest(target=measure, time_signature=time_signature)

        for move in ordered:
            target_index, position = move.target
            yield UpdateTemporalAnchorRequest(
                target=move.anchor,
                measure=targets[target_index],
                position=position,
            )

        for measure in shrinking:
            yield UpdateMeasureTimeSignatureRequest(target=measure, time_signature=time_signature)

        for measure in removed:
            yield DeleteEmptyMeasureRequest(target=measure, document=document)
