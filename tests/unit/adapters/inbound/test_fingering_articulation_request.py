import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import (
    SetArticulationRequest,
    SetFingeringRequest,
    ToggleArticulationRequest,
)
from piano_app.domain.score.document.models.notation import Articulation, Fingering
from piano_app.domain.score.document.services.mutation.compiler import (
    SetArticulationIntent,
    SetFingeringIntent,
    ToggleArticulationIntent,
)


@pytest.mark.unit
def test_a_fingering_request_sets_the_fingering_of_its_note() -> None:
    request: SetFingeringRequest = SetFingeringRequest.model_validate(
        {"note_id": "a", "fingering": 3}
    )

    assert request.to_intent() == SetFingeringIntent(note_id="a", fingering=Fingering.MIDDLE)


@pytest.mark.unit
def test_an_articulation_request_sets_the_articulation_of_its_carrier() -> None:
    request: SetArticulationRequest = SetArticulationRequest.model_validate(
        {"carrier_id": "a", "articulations": ["tenuto", "accent"]}
    )

    assert request.to_intent() == SetArticulationIntent(
        carrier_id="a",
        articulations=frozenset({Articulation.TENUTO, Articulation.ACCENT}),
    )


@pytest.mark.unit
@pytest.mark.parametrize("fingering", [6, -1, "thumb"])
def test_a_malformed_fingering_is_rejected_at_the_edge(fingering: object) -> None:
    with pytest.raises(ValidationError):
        SetFingeringRequest.model_validate({"note_id": "a", "fingering": fingering})


@pytest.mark.unit
def test_a_malformed_articulation_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        SetArticulationRequest.model_validate({"carrier_id": "a", "articulations": ["legato"]})


@pytest.mark.unit
def test_a_toggle_request_names_one_mark() -> None:
    request: ToggleArticulationRequest = ToggleArticulationRequest.model_validate(
        {"carrier_id": "a", "articulation": "marcato"}
    )

    assert request.to_intent() == ToggleArticulationIntent(
        carrier_id="a",
        articulation=Articulation.MARCATO,
    )
