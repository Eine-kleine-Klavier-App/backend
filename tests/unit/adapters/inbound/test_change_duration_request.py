import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import ChangeDurationRequest
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicValue
from piano_app.domain.score.document.services.mutation.compiler import ChangeDurationIntent


@pytest.mark.unit
def test_a_duration_request_changes_the_written_value_of_its_carrier() -> None:
    request: ChangeDurationRequest = ChangeDurationRequest.model_validate(
        {"carrier_id": "a", "written_value": {"value": 2, "dots": 1}}
    )

    assert request.to_intent() == ChangeDurationIntent(
        carrier_id="a",
        written_value=DottedRhythmicValue(value=RhythmicValue.HALF, dots_count=1),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "written_value",
    [{"value": 3}, {"value": 4, "dots": -1}, {"value": 32, "dots": 1}],
)
def test_a_malformed_written_value_is_rejected_at_the_edge(written_value: object) -> None:
    with pytest.raises(ValidationError):
        ChangeDurationRequest.model_validate({"carrier_id": "a", "written_value": written_value})
