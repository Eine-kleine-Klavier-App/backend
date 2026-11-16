from fractions import Fraction

from tests.unit.domain.scene import build_score, note_at, quarters

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)


def test_view_exposes_placement_capabilities_and_revision_separately_from_music():
    score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    target = PresentationTarget(
        entity_id=note_at(score=score, at=Fraction(0)).note_carrier.id,
        reference=ReferencePoint.STEM_TIP,
    )
    score.document.presentation.set_vertical(target=target, value=VerticalOffset(value=-0.75))
    view = ScoreView(document=score.document).jsonify()
    assert view["music_revision"] == score.document.music_revision
    assert view["presentation"]["vertical"] == [
        {"entity_id": target.entity_id, "reference": "stem_tip", "offset": -0.75}
    ]
    assert all("stem" not in row for row in view["carriers"])
    assert any(
        row["entity_id"] == target.entity_id and row["vertical"] and row["directed"]
        for row in view["presentation_capabilities"]
    )
