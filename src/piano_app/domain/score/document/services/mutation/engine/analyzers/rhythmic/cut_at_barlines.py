from fractions import Fraction

from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CutAtBarlinesRequest,
    ResizeSpanRequest,
)


class CutAtBarlinesAnalyzer:
    """Cuts every leaf starting in the given measures that crosses a barline
    (time-signature-change: notes tied, rests plain).

    Each is resized to its own written value: the resize cuts it at the barlines, keeps the
    leaf itself as the first piece, spells the pieces in its scope's units, ties the notes
    piece to piece and keeps an outgoing tie from the last piece while it still touches. A
    group crossing a barline stays whole.

    Decided before the first yield: each resize reads its own leaf on the live document and
    takes only the room that leaf already takes, so it never meets another.
    """

    def analyze(
        self,
        *,
        request: CutAtBarlinesRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        if not request.measures:
            return

        crossing: list[LeafRhythmicContainer] = []
        for measure in request.measures:
            measure_end: Fraction = geometry.measure_span(measure=measure).end
            for anchor in measure.anchors:
                for container in anchor.containers:
                    if not isinstance(container, LeafRhythmicContainer):
                        continue

                    if geometry.global_span_of(container=container).end <= measure_end:
                        continue

                    if container.written_size.count != 1:
                        raise ValueError("A leaf is written as one value.")

                    crossing.append(container)

        for leaf in crossing:
            yield ResizeSpanRequest(leaf=leaf, written_value=leaf.written_size.value)
