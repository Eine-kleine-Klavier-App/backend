import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import EditPresentationRequest
from piano_app.domain.score.document.models.notation import StemDirection
from piano_app.domain.score.document.services.presentation import SetDirection, SetVerticalOffset


def test_stem_direction_and_offset_decode_as_two_shared_capabilities():
    request = EditPresentationRequest.model_validate(
        {
            "changes": [
                {
                    "kind": "direction",
                    "target": {"entity_id": "a", "reference": "stem_tip"},
                    "direction": "down",
                },
                {
                    "kind": "vertical",
                    "target": {"entity_id": "a", "reference": "stem_tip"},
                    "offset": -0.75,
                },
            ]
        }
    )
    direction, vertical = request.to_commands()
    assert isinstance(direction, SetDirection) and direction.value is StemDirection.DOWN
    assert isinstance(vertical, SetVerticalOffset) and vertical.value.value == -0.75


@pytest.mark.parametrize("kind,value", [("direction", "sideways"), ("vertical", float("inf"))])
def test_invalid_presentation_values_rejected(kind, value):
    with pytest.raises(ValidationError):
        EditPresentationRequest.model_validate(
            {
                "changes": [
                    {
                        "kind": kind,
                        "target": {"entity_id": "a", "reference": "stem_tip"},
                        "direction" if kind == "direction" else "offset": value,
                    }
                ]
            }
        )
