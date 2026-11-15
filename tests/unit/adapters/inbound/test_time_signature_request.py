import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import ChangeTimeSignatureRequest
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    ChangeTimeSignatureIntent,
)


@pytest.mark.unit
def test_a_time_signature_request_gives_its_measures_the_signature() -> None:
    request: ChangeTimeSignatureRequest = ChangeTimeSignatureRequest.model_validate(
        {"measure_ids": ["a", "b"], "time_signature": {"value": {"value": 8}, "count": 6}}
    )

    assert request.to_intent() == ChangeTimeSignatureIntent(
        measure_ids=("a", "b"),
        time_signature=RhythmicSize(
            value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
            count=6,
        ),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "time_signature",
    [{"value": {"value": 4}, "count": 0}, {"value": {"value": 3}, "count": 3}, {"count": 3}],
)
def test_a_malformed_time_signature_is_rejected_at_the_edge(time_signature: object) -> None:
    with pytest.raises(ValidationError):
        ChangeTimeSignatureRequest.model_validate(
            {"measure_ids": ["a"], "time_signature": time_signature}
        )
