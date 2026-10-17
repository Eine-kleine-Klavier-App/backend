import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import SetStemsRequest
from piano_app.domain.score.document.models.notation import StemDirection, StemOverride
from piano_app.domain.score.document.services.mutation.compiler import (
    ResetStemIntent,
    SetStemIntent,
)


@pytest.mark.unit
def test_an_override_sets_the_stems() -> None:
    request: SetStemsRequest = SetStemsRequest.model_validate(
        {"carrier_ids": ["a", "b"], "override": {"direction": "up", "length_percent": 120}}
    )

    assert request.to_intent() == SetStemIntent(
        carrier_ids=("a", "b"),
        override=StemOverride(direction=StemDirection.UP, length_percent=120),
    )


@pytest.mark.unit
def test_a_null_override_resets_the_stems() -> None:
    request: SetStemsRequest = SetStemsRequest.model_validate(
        {"carrier_ids": ["a"], "override": None}
    )

    assert request.to_intent() == ResetStemIntent(carrier_ids=("a",))


@pytest.mark.unit
def test_a_length_left_out_means_the_default_length() -> None:
    request: SetStemsRequest = SetStemsRequest.model_validate(
        {"carrier_ids": ["a"], "override": {"direction": "down"}}
    )

    assert request.to_intent() == SetStemIntent(
        carrier_ids=("a",),
        override=StemOverride(direction=StemDirection.DOWN),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        {"direction": "up", "length_percent": 0},
        {"direction": "sideways"},
    ],
)
def test_a_malformed_override_is_rejected_at_the_edge(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SetStemsRequest.model_validate({"carrier_ids": ["a"], "override": override})
