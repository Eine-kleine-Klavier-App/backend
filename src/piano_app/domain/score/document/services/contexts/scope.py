from dataclasses import dataclass

from piano_app.domain.score.document.models.context import Context, StaffScoped, VoiceScoped
from piano_app.domain.score.document.models.structural import Staff, Voice


@dataclass(frozen=True, slots=True, kw_only=True)
class Scope:
    """What a context governs, as a key: the whole score, one staff or one voice."""

    staff: Staff | None = None
    voice: Voice | None = None

    def __post_init__(self) -> None:
        if self.staff is not None and self.voice is not None:
            raise ValueError("A scope is the score, a staff or a voice, not two of them.")

    @classmethod
    def score(cls) -> Scope:
        return cls()

    @classmethod
    def of_staff(cls, *, staff: Staff) -> Scope:
        return cls(staff=staff)

    @classmethod
    def of_voice(cls, *, voice: Voice) -> Scope:
        return cls(voice=voice)


def scope_of(*, context: Context) -> Scope:
    """The scope a context governs: its staff, its voice, or the whole score."""
    if isinstance(context, StaffScoped):
        return Scope.of_staff(staff=context.staff)

    if isinstance(context, VoiceScoped):
        return Scope.of_voice(voice=context.voice)

    return Scope.score()
