import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import InsertMeasureRequest
from piano_app.domain.score.document.services.mutation.compiler import (
    AppendMeasureIntent,
    InsertMeasureIntent,
)


@pytest.mark.unit
def test_a_measure_request_naming_a_measure_inserts_before_it() -> None:
    request: InsertMeasureRequest = InsertMeasureRequest.model_validate({"before_measure_id": "m"})

    assert request.to_intent() == InsertMeasureIntent(before_measure_id="m")


@pytest.mark.unit
@pytest.mark.parametrize("body", [{}, {"before_measure_id": None}], ids=["left-out", "null"])
def test_a_measure_request_naming_no_measure_appends_one(body: dict[str, object]) -> None:
    request: InsertMeasureRequest = InsertMeasureRequest.model_validate(body)

    assert request.to_intent() == AppendMeasureIntent()


@pytest.mark.unit
def test_a_malformed_measure_id_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        InsertMeasureRequest.model_validate({"before_measure_id": 3})
