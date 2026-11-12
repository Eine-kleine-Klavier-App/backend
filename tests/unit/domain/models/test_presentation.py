import pytest

from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    Presentation,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_placement_values_are_refused(value):
    for factory in (
        lambda: VerticalOffset(value=value),
        lambda: EndpointOffsets(left=value),
        lambda: EndpointOffsets(right=value),
    ):
        with pytest.raises(ValueError):
            factory()


def test_reference_points_do_not_share_values_and_public_maps_are_readonly():
    presentation = Presentation()
    body = PresentationTarget(entity_id="same")
    tip = PresentationTarget(entity_id="same", reference=ReferencePoint.STEM_TIP)
    presentation.set_vertical(target=body, value=VerticalOffset(value=0))
    presentation.set_vertical(target=tip, value=VerticalOffset(value=-1))
    assert presentation.vertical[body].value == 0
    assert presentation.vertical[tip].value == -1
    with pytest.raises(TypeError):
        presentation.vertical[body] = VerticalOffset(value=2)
    presentation.set_vertical(target=body, value=None)
    assert body not in presentation.vertical and tip in presentation.vertical
