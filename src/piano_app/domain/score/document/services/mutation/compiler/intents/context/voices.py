from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class AddContextVoiceIntent(EditIntent):
    """Make a context apply to one more voice."""

    context_id: str
    voice_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveContextVoiceIntent(EditIntent):
    """Make a context stop applying to one of its voices, keeping its remaining scope."""

    context_id: str
    voice_id: str
