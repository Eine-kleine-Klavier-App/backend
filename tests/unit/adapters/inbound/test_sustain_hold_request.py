import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import CreateSustainHoldRequest
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import CreateSustainHoldIntent


@pytest.mark.unit
def test_a_sustain_hold_request_names_its_two_places() -> None:
    request: CreateSustainHoldRequest = CreateSustainHoldRequest.model_validate(
        {
            "start_measure_id": "a",
            "start_position": {"numerator": 0, "denominator": 1},
            "end_measure_id": "b",
            "end_position": {"numerator": 1, "denominator": 2},
        }
    )

    assert request.to_intent() == CreateSustainHoldIntent(
        start_measure_id="a",
        start_position=MeasurePosition.of(numerator=0, denominator=1),
        end_measure_id="b",
        end_position=MeasurePosition.of(numerator=1, denominator=2),
    )


@pytest.mark.unit
def test_a_sustain_hold_request_without_an_end_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        CreateSustainHoldRequest.model_validate(
            {"start_measure_id": "a", "start_position": {"numerator": 0, "denominator": 1}}
        )
