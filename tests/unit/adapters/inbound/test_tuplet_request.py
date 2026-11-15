import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import CreateTupletRequest
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
)

# A triplet of eighths on beat two: three eighths written where two sound.
_TRIPLET: dict[str, object] = {
    "voice_id": "v",
    "staff_id": "s",
    "measure_id": "m",
    "position": {"numerator": 1, "denominator": 4},
    "written_size": {"value": {"value": 8}, "count": 3},
    "occupied_size": {"value": {"value": 8}, "count": 2},
    "written_value": {"value": 8},
}
_EIGHTH: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.EIGHTH)


@pytest.mark.unit
def test_a_tuplet_request_with_a_note_starts_the_tuplet_with_that_note() -> None:
    request: CreateTupletRequest = CreateTupletRequest.model_validate(
        {**_TRIPLET, "note": {"staff_step": 2, "accidental": "sharp", "fingering": 1}}
    )

    assert request.to_intent() == CreateTupletWithNoteIntent(
        voice_id="v",
        staff_id="s",
        measure_id="m",
        position=MeasurePosition.of(numerator=1, denominator=4),
        written_size=RhythmicSize(value=_EIGHTH, count=3),
        occupied_size=RhythmicSize(value=_EIGHTH, count=2),
        written_value=_EIGHTH,
        staff_step=2,
        accidental=Accidental.SHARP,
        fingering=Fingering.THUMB,
    )


@pytest.mark.unit
def test_a_tuplet_request_with_a_null_note_starts_the_tuplet_with_a_rest() -> None:
    request: CreateTupletRequest = CreateTupletRequest.model_validate({**_TRIPLET, "note": None})

    assert request.to_intent() == CreateTupletWithRestIntent(
        voice_id="v",
        staff_id="s",
        measure_id="m",
        position=MeasurePosition.of(numerator=1, denominator=4),
        written_size=RhythmicSize(value=_EIGHTH, count=3),
        occupied_size=RhythmicSize(value=_EIGHTH, count=2),
        written_value=_EIGHTH,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "change",
    [
        pytest.param({}, id="note-left-out"),
        pytest.param(
            {"note": None, "occupied_size": {"value": {"value": 8}, "count": 0}},
            id="empty-size",
        ),
    ],
)
def test_a_malformed_tuplet_is_rejected_at_the_edge(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CreateTupletRequest.model_validate({**_TRIPLET, **change})
