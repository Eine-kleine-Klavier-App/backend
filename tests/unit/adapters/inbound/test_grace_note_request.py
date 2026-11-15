import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import (
    AddGraceCarrierNoteRequest,
    AddGraceNoteRequest,
    ChangeGraceTypeRequest,
    ChangeGraceValueRequest,
    RemoveGraceNoteRequest,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    ChangeGraceTypeIntent,
    ChangeGraceValueIntent,
    RemoveGraceNoteIntent,
)

_GRACE: dict[str, object] = {
    "host_carrier_id": "c",
    "placement": "before",
    "grace_type": "acciaccatura",
    "written_value": {"value": 16},
    "staff_id": "s",
    "staff_step": 2,
}


@pytest.mark.unit
def test_a_grace_note_request_becomes_the_intent_with_what_it_names() -> None:
    request: AddGraceNoteRequest = AddGraceNoteRequest.model_validate(
        {**_GRACE, "accidental": "sharp", "fingering": 1}
    )

    assert request.to_intent() == AddGraceNoteIntent(
        host_carrier_id="c",
        placement=GracePlacement.BEFORE,
        grace_type=GraceType.ACCIACCATURA,
        written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
        staff_id="s",
        staff_step=2,
        accidental=Accidental.SHARP,
        fingering=Fingering.THUMB,
    )


@pytest.mark.unit
def test_a_grace_note_request_without_a_sign_leaves_it_to_be_inferred() -> None:
    intent: AddGraceNoteIntent = AddGraceNoteRequest.model_validate(_GRACE).to_intent()

    assert intent.accidental is None
    assert intent.fingering is Fingering.NONE


@pytest.mark.unit
def test_a_grace_note_request_needs_its_placement_and_kind() -> None:
    with pytest.raises(ValidationError):
        AddGraceNoteRequest.model_validate({**_GRACE, "placement": "between"})
    with pytest.raises(ValidationError):
        AddGraceNoteRequest.model_validate({**_GRACE, "grace_type": "slurred"})


@pytest.mark.unit
def test_a_removal_request_names_the_note() -> None:
    request: RemoveGraceNoteRequest = RemoveGraceNoteRequest.model_validate({"note_id": "n"})

    assert request.to_intent() == RemoveGraceNoteIntent(note_id="n")


@pytest.mark.unit
def test_a_type_change_request_names_the_note_and_the_kind() -> None:
    request: ChangeGraceTypeRequest = ChangeGraceTypeRequest.model_validate(
        {"note_id": "n", "grace_type": "acciaccatura"}
    )

    assert request.to_intent() == ChangeGraceTypeIntent(
        note_id="n", grace_type=GraceType.ACCIACCATURA
    )
    with pytest.raises(ValidationError):
        ChangeGraceTypeRequest.model_validate({"note_id": "n", "grace_type": "slurred"})


@pytest.mark.unit
def test_a_grace_note_request_may_name_the_carrier_it_stands_after() -> None:
    intent: AddGraceNoteIntent = AddGraceNoteRequest.model_validate(
        {**_GRACE, "after_carrier_id": "g"}
    ).to_intent()

    assert intent.after_carrier_id == "g"
    assert AddGraceNoteRequest.model_validate(_GRACE).to_intent().after_carrier_id is None


@pytest.mark.unit
def test_a_request_to_join_a_grace_carrier_names_it_and_the_note() -> None:
    request: AddGraceCarrierNoteRequest = AddGraceCarrierNoteRequest.model_validate(
        {"carrier_id": "g", "staff_id": "s", "staff_step": 2, "accidental": "flat"}
    )

    assert request.to_intent() == AddGraceCarrierNoteIntent(
        carrier_id="g",
        staff_id="s",
        staff_step=2,
        accidental=Accidental.FLAT,
        fingering=Fingering.NONE,
    )


@pytest.mark.unit
def test_a_value_change_request_names_the_carrier_and_the_value() -> None:
    request: ChangeGraceValueRequest = ChangeGraceValueRequest.model_validate(
        {"carrier_id": "g", "written_value": {"value": 8, "dots": 1}}
    )

    assert request.to_intent() == ChangeGraceValueIntent(
        carrier_id="g",
        written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH, dots_count=1),
    )
