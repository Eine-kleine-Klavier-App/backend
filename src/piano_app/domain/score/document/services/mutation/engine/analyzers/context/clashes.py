from collections.abc import Sequence

from piano_app.domain.score.document.models.context import Context, VoicesScoped
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.contexts import (
    Clash,
    ClashKind,
    KindPolicy,
    OnSamePlace,
    policy_of,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    UpdateContextVoicesRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


def refuse_clashes(*, clashes: Sequence[Clash]) -> None:
    """Refuses a placement that meets anything but a context at its own place: that one a
    creation displaces (``displace_same_place``), everything else it may not share the
    timeline with."""
    for clash in clashes:
        if clash.kind is not ClashKind.SAME_PLACE:
            raise MutationRejectedError(clash.reason)


def displace_same_place(
    *,
    clashes: Sequence[Clash],
    voices: Sequence[Voice] | None,
) -> MutationAnalysis:
    """Clears what a new context finds at its own place, each by the policy of its kind: a
    context that is replaced is deleted; one that is cut down loses the voices of the new
    context, and is deleted when none is left."""
    for clash in clashes:
        if clash.kind is not ClashKind.SAME_PLACE:
            continue

        policy: KindPolicy | None = policy_of(kind=type(clash.context))
        if policy is None:
            continue

        if policy.on_same_place is OnSamePlace.REPLACE:
            yield DeleteRequest(target=clash.context)
        elif policy.on_same_place is OnSamePlace.SUBTRACT_VOICES:
            existing: Context = clash.context
            if not isinstance(existing, VoicesScoped):
                raise TypeError(f"{type(existing).__name__} names no voices to subtract.")

            remaining: tuple[Voice, ...] = tuple(
                voice for voice in existing.voices if voice not in (voices or ())
            )
            if remaining:
                yield UpdateContextVoicesRequest(target=existing, voices=remaining)
            else:
                yield DeleteRequest(target=existing)
