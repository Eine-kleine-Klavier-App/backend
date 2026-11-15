import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.score.edit.requests import (
    AddContextVoiceRequest,
    RemoveContextVoiceRequest,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    AddContextVoiceIntent,
    RemoveContextVoiceIntent,
)


@pytest.mark.unit
def test_a_context_voice_request_names_the_context_and_the_voice() -> None:
    body: dict[str, str] = {"context_id": "slur-1", "voice_id": "voice-2"}

    assert AddContextVoiceRequest.model_validate(body).to_intent() == AddContextVoiceIntent(
        context_id="slur-1", voice_id="voice-2"
    )
    assert RemoveContextVoiceRequest.model_validate(body).to_intent() == RemoveContextVoiceIntent(
        context_id="slur-1", voice_id="voice-2"
    )


@pytest.mark.unit
def test_a_context_voice_request_without_a_voice_is_rejected_at_the_edge() -> None:
    with pytest.raises(ValidationError):
        AddContextVoiceRequest.model_validate({"context_id": "slur-1"})
