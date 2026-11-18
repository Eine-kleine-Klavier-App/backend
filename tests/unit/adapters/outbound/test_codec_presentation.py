from fractions import Fraction

from tests.unit.domain.mutation.scenarios.test_intent_split_beam import _line
from tests.unit.domain.scene import note_at

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)


def test_the_presentation_is_saved_as_ratios_and_read_back():
    score, _, beam = _line(4)
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    stem = PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
    score.document.presentation.set_vertical(target=stem, value=VerticalOffset(value=1.5))
    score.document.presentation.set_endpoints(
        target=PresentationTarget(entity_id=beam.id), value=EndpointOffsets(left=0.75, right=1.25)
    )
    codec = ScoreDocumentCodec()

    data = codec.serialize(score.document)
    restored = codec.deserialize(data)

    assert restored.presentation.vertical[stem].value == 1.5
    value = restored.presentation.endpoints[PresentationTarget(entity_id=beam.id)]
    assert (value.left, value.right) == (0.75, 1.25)
    assert codec.serialize(restored) == data
