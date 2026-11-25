import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import EditPresentationRequest


@pytest.mark.parametrize(
    "changes",
    [
        [],
        [{"kind": "colour", "target": {"entity_id": "x"}, "value": "red"}],
        [{"kind": "vertical", "target": {"entity_id": "", "reference": "body"}, "offset": 0}],
        [{"kind": "vertical", "target": {"entity_id": "x", "reference": "wrong"}, "offset": 0}],
        [
            {
                "kind": "vertical",
                "target": {"entity_id": "x", "reference": "body"},
                "offset": 0,
                "accidental": "sharp",
            }
        ],
    ],
)
def test_bad_presentation_batches_are_422_at_the_edge(changes):
    with pytest.raises(ValidationError):
        EditPresentationRequest.model_validate({"changes": changes})


def test_an_edge_move_carries_its_presentation_changes_into_the_same_request():
    from piano_app.adapters.inbound.http.score.edit.requests import MoveContextEndRequest
    from piano_app.domain.score.document.models.presentation import ReferencePoint
    from piano_app.domain.score.document.services.presentation import SetVerticalOffset

    request = MoveContextEndRequest.model_validate(
        {
            "context_ids": ["s"],
            "measure_id": "m",
            "position": {"numerator": 1, "denominator": 4},
            "mode": "preserve_step",
            "presentation": [
                {
                    "kind": "vertical",
                    "target": {"entity_id": "s", "reference": "height"},
                    "offset": 2.5,
                }
            ],
        }
    )

    (command,) = request.to_presentation()
    assert isinstance(command, SetVerticalOffset)
    assert command.target.reference is ReferencePoint.HEIGHT
    assert command.value is not None and command.value.value == 2.5
    assert (
        MoveContextEndRequest.model_validate(
            {
                "context_ids": ["s"],
                "measure_id": "m",
                "position": {"numerator": 1, "denominator": 4},
                "mode": "preserve_step",
            }
        ).to_presentation()
        == []
    )
