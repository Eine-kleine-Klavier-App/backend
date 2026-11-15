import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import SetCarrierMarksRequest
from piano_app.domain.score.document.models.notation import Articulation, Ornament
from piano_app.domain.score.document.services.mutation.compiler import (
    CarrierMarks,
    SetCarrierMarksIntent,
)


@pytest.mark.unit
def test_a_batch_request_becomes_one_intent_and_a_missing_mark_stays_untouched() -> None:
    request: SetCarrierMarksRequest = SetCarrierMarksRequest.model_validate(
        {
            "items": [
                {"carrier_id": "a", "ornament": "trill"},
                {"carrier_id": "b", "articulations": ["accent", "arpeggio_up"]},
                {"carrier_id": "c", "articulations": [], "ornament": "none"},
            ]
        }
    )

    assert request.to_intent() == SetCarrierMarksIntent(
        items=(
            CarrierMarks(carrier_id="a", ornament=Ornament.TRILL),
            CarrierMarks(
                carrier_id="b",
                articulations=frozenset({Articulation.ACCENT, Articulation.ARPEGGIO_UP}),
            ),
            CarrierMarks(carrier_id="c", articulations=frozenset(), ornament=Ornament.NONE),
        )
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {},
        {"items": [{"carrier_id": "a", "ornament": "tremolo"}]},
        {"items": [{"carrier_id": "a", "articulations": ["trill"]}]},
    ],
)
def test_a_malformed_batch_is_rejected_at_the_edge(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SetCarrierMarksRequest.model_validate(body)
