from collections.abc import Sequence

from piano_app.domain.score.document.services.contexts import (
    Clash,
    ClashKind,
    KindPolicy,
    OnSamePlace,
    policy_of,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
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


def displace_same_place(*, clashes: Sequence[Clash]) -> MutationAnalysis:
    """Clears what a new context finds at its own place, each by the policy of its kind: a
    context that is replaced is deleted."""
    for clash in clashes:
        if clash.kind is not ClashKind.SAME_PLACE:
            continue

        policy: KindPolicy | None = policy_of(kind=type(clash.context))
        if policy is None:
            continue

        if policy.on_same_place is OnSamePlace.REPLACE:
            yield DeleteRequest(target=clash.context)
