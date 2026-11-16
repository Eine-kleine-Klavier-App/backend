from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.indexing import EntityIndex
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

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: EditIntent,
        entities: EntityIndex | None = None,
    ) -> Sequence[MutationRequest]:
        """The requests of the intent. ``entities`` is the index of the document's entities
        the ids of the intent are looked up in; a caller that compiles several intents over one
        document passes the one it keeps, otherwise one is made for this intent."""
        return self._registry.get(intent_type=type(intent)).compile(
            document=document,
            intent=intent,
            entities=entities if entities is not None else EntityIndex(document=document),
        )
