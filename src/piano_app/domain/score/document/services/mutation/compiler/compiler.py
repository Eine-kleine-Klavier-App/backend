from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest

from .base import EditIntent
from .registry import IntentCompilerRegistry


class MutationCompiler:
    """Entry / command-compiler: turns one user intent into the engine requests of
    one gesture, dispatching to the compiler registered for the intent's type.

    Deterministic — it only addresses (ids to entities, a click to voice, measure,
    position and length) and never mutates; every decision is taken on the live document
    by the analyzers.
    """

    def __init__(self, *, registry: IntentCompilerRegistry) -> None:
        self._registry: IntentCompilerRegistry = registry

    def compile(self, *, document: ScoreDocument, intent: EditIntent) -> Sequence[MutationRequest]:
        return self._registry.get(intent_type=type(intent)).compile(
            document=document,
            intent=intent,
        )
