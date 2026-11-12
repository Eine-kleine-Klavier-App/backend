from fractions import Fraction

from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.services.contexts.context_map import ContextMap
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry


def test_a_span_with_no_end_is_read_to_the_end_of_the_score() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=2, staff_count=2, measure_count=3
    )
    upper, _ = document.staffs
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, Fraction(1)), end=None, staff=upper, octaves=1
    )
    context_map: ContextMap = ContextMap(geometry=ScoreGeometry(document=document))

    region = context_map.region_of(context=line)
    overlapping = context_map.spans_overlapping(
        span_type=OctaveTransposition, start=Fraction(5, 2), end=Fraction(3), voices=None
    )
    across = context_map.spans_across(
        span_type=OctaveTransposition, start=Fraction(2), end=Fraction(5, 2), voices=None
    )

    assert region.end == Fraction(3)
    assert overlapping == [line]
    assert across == [line]
