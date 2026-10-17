from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.shared.abstract import abstract


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class EditIntent:
    """Role base: one user action, compiled into the requests of one gesture.

    Intents are dumb data records — entity ids as strings plus domain values; all
    behavior lives in the matching compiler.
    """


class IntentCompiler[I: EditIntent](Protocol):
    """Decomposes one intent into the ordered engine requests of one gesture.

    Reads the original document and never mutates it, so a compiler decides only what
    is computable before execution; anything depending on the effect of an earlier
    request belongs to the analyzers. To refuse an intent that cannot be decomposed,
    raise ``MutationRejectedError``.
    """

    def compile(self, *, document: ScoreDocument, intent: I) -> Sequence[MutationRequest]: ...
