import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import EditPresentationRequest
from piano_app.domain.score.document.models.presentation import (
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
)
from piano_app.domain.score.document.services.presentation import (
    SetHorizontalEndpointOffsets,
    SetHorizontalOffset,
)

_LOWER: dict[str, str] = {"entity_id": "slur", "reference": "lower_edge"}
_TARGET: PresentationTarget = PresentationTarget(
    entity_id="slur", reference=ReferencePoint.LOWER_EDGE
)


@pytest.mark.unit
def test_a_sideways_move_request_becomes_a_command() -> None:
    request: EditPresentationRequest = EditPresentationRequest.model_validate(
        {
            "changes": [
                {"kind": "horizontal", "target": _LOWER, "offset": -0.5},
                {
                    "kind": "horizontal_endpoints",
                    "target": _LOWER,
                    "offsets": {"left": 0.5, "right": -0.25},
                },
            ]
        }
    )

    assert request.to_commands() == [
        SetHorizontalOffset(target=_TARGET, value=HorizontalOffset(value=-0.5)),
        SetHorizontalEndpointOffsets(
            target=_TARGET, value=HorizontalEndpointOffsets(left=0.5, right=-0.25)
        ),
    ]


@pytest.mark.unit
def test_a_null_sideways_move_resets_it() -> None:
    request: EditPresentationRequest = EditPresentationRequest.model_validate(
        {
            "changes": [
                {"kind": "horizontal", "target": _LOWER, "offset": None},
                {"kind": "horizontal_endpoints", "target": _LOWER, "offsets": None},
            ]
        }
    )

    assert request.to_commands() == [
        SetHorizontalOffset(target=_TARGET, value=None),
        SetHorizontalEndpointOffsets(target=_TARGET, value=None),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "change",
    [
        {"kind": "horizontal", "target": _LOWER, "offset": float("nan")},
        {"kind": "horizontal", "target": _LOWER},
        {"kind": "horizontal", "target": _LOWER, "offset": 1, "extra": 1},
        {"kind": "horizontal_endpoints", "target": _LOWER, "offsets": {"left": 1}},
        {
            "kind": "horizontal_endpoints",
            "target": _LOWER,
            "offsets": {"left": 1, "right": float("inf")},
        },
        {"kind": "horizontal", "target": {"entity_id": "slur", "reference": "side"}, "offset": 1},
    ],
)
def test_bad_sideways_moves_are_refused_at_the_edge(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EditPresentationRequest.model_validate({"changes": [change]})
