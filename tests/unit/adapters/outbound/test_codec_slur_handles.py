from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor, score

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)

# The six handles of a slur are saved with the presentation; a record from before the sideways
# moves existed has none of them.


def _with_a_shaped_slur() -> tuple[ScoreDocument, PresentationTarget, PresentationTarget]:
    document: ScoreDocument = score()
    slur: Slur = Slur.create(
        start=anchor(document, Fraction(1)),
        end=anchor(document, Fraction(3, 2)),
        voices=[document.voices[0]],
    )
    top = PresentationTarget(entity_id=slur.id)
    lower = PresentationTarget(entity_id=slur.id, reference=ReferencePoint.LOWER_EDGE)
    presentation = document.presentation
    presentation.set_vertical(target=top, value=VerticalOffset(value=-1))
    presentation.set_endpoints(target=top, value=EndpointOffsets(left=0.5, right=-0.5))
    presentation.set_vertical(target=lower, value=VerticalOffset(value=1))
    presentation.set_endpoints(target=lower, value=EndpointOffsets(left=0.25, right=0.5))
    presentation.set_horizontal(target=lower, value=HorizontalOffset(value=-0.5))
    presentation.set_horizontal_endpoints(
        target=lower, value=HorizontalEndpointOffsets(left=0.5, right=-0.5)
    )

    return document, top, lower


@pytest.mark.unit
def test_the_handles_of_a_slur_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    document, top, lower = _with_a_shaped_slur()

    decoded: ScoreDocument = codec.deserialize(codec.serialize(document))

    presentation = decoded.presentation
    assert presentation.vertical[top] == VerticalOffset(value=-1)
    assert presentation.endpoints[lower] == EndpointOffsets(left=0.25, right=0.5)
    assert presentation.horizontal[lower] == HorizontalOffset(value=-0.5)
    assert presentation.horizontal_endpoints[lower] == HorizontalEndpointOffsets(
        left=0.5, right=-0.5
    )
    assert codec.serialize(decoded) == codec.serialize(document)
