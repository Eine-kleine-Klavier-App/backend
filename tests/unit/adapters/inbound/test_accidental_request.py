import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import SetAccidentalRequest
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.services.mutation.compiler import SetAccidentalIntent


@pytest.mark.unit
@pytest.mark.parametrize(
    ("wire", "accidental"),
    [("double_sharp", Accidental.DOUBLE_SHARP), ("double_flat", Accidental.DOUBLE_FLAT)],
)
def test_a_double_accidental_is_read_from_the_request(wire: str, accidental: Accidental) -> None:
    request: SetAccidentalRequest = SetAccidentalRequest.model_validate(
        {"note_id": "a", "accidental": wire}
    )

    assert request.to_intent() == SetAccidentalIntent(note_id="a", accidental=accidental)


@pytest.mark.unit
def test_a_triple_accidental_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        SetAccidentalRequest.model_validate({"note_id": "a", "accidental": "triple_sharp"})
