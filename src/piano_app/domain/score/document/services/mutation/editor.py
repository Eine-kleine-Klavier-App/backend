from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument

from .compiler import EditIntent, MutationCompiler
from .engine import MutationEngine
from .engine.log import MutationLog


class MutationEditor:
    """Applies a sequence of intents as one transaction — one undo step.

    Intent k is compiled against the live document intent k-1 left and run as its own
    pass, so each one is addressed and decided exactly as if it came alone. Any failure,
    a compiler refusal included, rolls back every intent before it.

    Here rather than in the compiler, which never executes, or the engine, which knows
    requests but not intents: the sequencing needs both, and that one batch is one undo
    step is a rule of the editor, not of its callers.
    """

    def __init__(self, *, compiler: MutationCompiler, engine: MutationEngine) -> None:
        self._compiler: MutationCompiler = compiler
        self._engine: MutationEngine = engine

    def apply(self, *, document: ScoreDocument, intents: Sequence[EditIntent]) -> MutationLog:
        with self._engine.transaction(document=document) as transaction:
            for intent in intents:
                transaction.run(
                    requests=self._compiler.compile(
                        document=document, intent=intent, entities=transaction.entities
                    )
                )

        return transaction.log
