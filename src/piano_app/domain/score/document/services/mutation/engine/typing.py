from collections.abc import Generator

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationAction,
    MutationRequest,
)

"""What an analyzer emits: a further request to expand, or a terminal action."""
type MutationWorkItem = MutationRequest | MutationAction

"""One analyzer run: it yields work items one at a time and is sent back what each one
produced — a request's sent-back entity, an action's handler result, or None — so it
continues against the live document. It returns nothing: its request sends back its
terminal's result, if it has one. A create yields its terminal; one that may find what it
needs instead of creating it leaves that to its caller.
"""
type MutationAnalysis = Generator[MutationWorkItem, ScoreEntity | None]
