from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor, score

from piano_app.application.use_cases.score.shared.view import ScoreView
from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.presentation import (
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
)

# The view tells the editor which handles a target has and what they are set to.


@pytest.mark.unit
def test_the_view_gives_a_slur_its_two_edges_and_their_sideways_moves() -> None:
    document = score()
    slur: Slur = Slur.create(
        start=anchor(document, Fraction(1)),
        end=anchor(document, Fraction(3, 2)),
        voices=[document.voices[0]],
    )
    lower = PresentationTarget(entity_id=slur.id, reference=ReferencePoint.LOWER_EDGE)
    document.presentation.set_horizontal(target=lower, value=HorizontalOffset(value=-0.5))
    document.presentation.set_horizontal_endpoints(
        target=lower, value=HorizontalEndpointOffsets(left=0.5, right=-0.25)
    )

    data = ScoreView(document=document).jsonify()

    capabilities = {
        (row["entity_id"], row["reference"]): row
        for row in data["presentation_capabilities"]
        if row["entity_id"] == slur.id
    }
    top = capabilities[(slur.id, "body")]
    lower_row = capabilities[(slur.id, "lower_edge")]
    assert (top["endpoints"], top["horizontal"], top["horizontal_endpoints"]) == (
        True,
        False,
        False,
    )
    assert (lower_row["horizontal"], lower_row["horizontal_endpoints"]) == (True, True)
    assert data["presentation"]["horizontal"] == [
        {"entity_id": slur.id, "reference": "lower_edge", "offset": -0.5}
    ]
    assert data["presentation"]["horizontal_endpoints"] == [
        {"entity_id": slur.id, "reference": "lower_edge", "left": 0.5, "right": -0.25}
    ]
