import pytest

from piano_app.domain.score.document.models.presentation import (
    HorizontalEndpointOffsets,
    HorizontalOffset,
)

# A sideways move is a number of staff spaces, positive to the right. The model checks only that
# it is a number; how far a handle may go is the renderer's to decide, as for the vertical ones.


@pytest.mark.unit
def test_sideways_moves_either_way_are_accepted() -> None:
    HorizontalOffset(value=-1.5)
    HorizontalOffset(value=2)
    HorizontalEndpointOffsets(left=0.5, right=-0.5)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_sideways_move_that_is_not_a_number_is_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        HorizontalOffset(value=bad)

    with pytest.raises(ValueError, match="finite"):
        HorizontalEndpointOffsets(left=bad)

    with pytest.raises(ValueError, match="finite"):
        HorizontalEndpointOffsets(right=bad)
