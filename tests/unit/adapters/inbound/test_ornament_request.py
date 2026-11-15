import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import SetOrnamentRequest
from piano_app.domain.score.document.models.notation import Ornament
from piano_app.domain.score.document.services.mutation.compiler import SetOrnamentIntent


@pytest.mark.unit
def test_an_ornament_request_sets_the_ornament_of_its_carrier() -> None:
    request: SetOrnamentRequest = SetOrnamentRequest.model_validate(
        {"carrier_id": "a", "ornament": "lower_mordent"}
    )

    assert request.to_intent() == SetOrnamentIntent(
        carrier_id="a",
        ornament=Ornament.LOWER_MORDENT,
    )


@pytest.mark.unit
def test_an_ornament_request_takes_a_tremolo_by_its_strokes() -> None:
    request: SetOrnamentRequest = SetOrnamentRequest.model_validate(
        {"carrier_id": "a", "ornament": "tremolo_3"}
    )

    assert request.to_intent() == SetOrnamentIntent(carrier_id="a", ornament=Ornament.TREMOLO_3)


@pytest.mark.unit
def test_a_malformed_ornament_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        SetOrnamentRequest.model_validate({"carrier_id": "a", "ornament": "tremolo"})
