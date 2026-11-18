from fractions import Fraction

from tests.unit.domain.scene import build_score, note_at, quarters

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models.notation import StemDirection
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)


def test_stem_placement_survives_roundtrip_outside_carrier():
    score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    target = PresentationTarget(
        entity_id=note_at(score=score, at=Fraction(0)).note_carrier.id,
        reference=ReferencePoint.STEM_TIP,
    )
    score.document.presentation.set_vertical(target=target, value=VerticalOffset(value=-1.75))
    score.document.presentation.set_direction(target=target, value=StemDirection.UP)
    codec = ScoreDocumentCodec()
    data = codec.serialize(score.document)
    assert all("stem" not in row for row in data["tables"]["carriers"].values())
    restored = codec.deserialize(data)
    assert restored.presentation.vertical[target].value == -1.75
    assert restored.presentation.directions[target] is StemDirection.UP
    assert codec.serialize(restored) == data
