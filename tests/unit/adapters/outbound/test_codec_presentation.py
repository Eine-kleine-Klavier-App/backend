from fractions import Fraction

import pytest
from tests.unit.domain.mutation.scenarios.test_intent_split_beam import _line
from tests.unit.domain.scene import four_quarters, note_at

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models.notation import StemDirection
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("percent", [50, 100, 150])
def test_a_legacy_stem_percentage_becomes_a_factor_of_the_automatic_length(direction, percent):
    score = four_quarters()
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    codec = ScoreDocumentCodec()
    legacy = codec.serialize(score.document)
    legacy.pop("presentation")
    next(row for row in legacy["carriers"] if row["id"] == carrier.id)["stem"] = {
        "direction": direction,
        "length_percent": percent,
    }
    restored = codec.deserialize(legacy)
    target = PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
    assert restored.presentation.directions[target] is StemDirection(direction)
    if percent == 100:
        assert target not in restored.presentation.vertical
    else:
        assert restored.presentation.vertical[target].value == percent / 100
    new = codec.serialize(restored)
    assert "stem" not in next(row for row in new["carriers"] if row["id"] == carrier.id)
    assert codec.serialize(codec.deserialize(new)) == new


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

    assert data["presentation"]["units"] == "ratio"
    assert restored.presentation.vertical[stem].value == 1.5
    value = restored.presentation.endpoints[PresentationTarget(entity_id=beam.id)]
    assert (value.left, value.right) == (0.75, 1.25)
    assert codec.serialize(restored) == data


def test_distances_saved_in_the_old_units_are_dropped_and_directions_kept():
    score, _, beam = _line(4)
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    stem = PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
    score.document.presentation.set_direction(target=stem, value=StemDirection.DOWN)
    score.document.presentation.set_vertical(target=stem, value=VerticalOffset(value=-1.25))
    score.document.presentation.set_endpoints(
        target=PresentationTarget(entity_id=beam.id), value=EndpointOffsets(left=-1.5, right=2.25)
    )
    codec = ScoreDocumentCodec()
    old = codec.serialize(score.document)
    old["presentation"].pop("units")

    restored = codec.deserialize(old)

    assert not restored.presentation.vertical
    assert not restored.presentation.endpoints
    assert restored.presentation.directions[stem] is StemDirection.DOWN
