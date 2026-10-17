from .compiler import MutationCompiler
from .create import (
    CreateTupletWithNoteCompiler,
    CreateTupletWithRestCompiler,
    InsertNoteCompiler,
    TieNotesCompiler,
)
from .delete import DeleteBatchCompiler
from .intents import (
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
    DeleteBatchIntent,
    InsertNoteIntent,
    ResetStemIntent,
    SetStemIntent,
    TieNotesIntent,
)
from .registry import IntentCompilerRegistry
from .update import ResetStemCompiler, SetStemCompiler


def _build_registry() -> IntentCompilerRegistry:
    registry: IntentCompilerRegistry = IntentCompilerRegistry()

    registry.register(intent_type=InsertNoteIntent, compiler=InsertNoteCompiler())
    registry.register(intent_type=TieNotesIntent, compiler=TieNotesCompiler())
    registry.register(
        intent_type=CreateTupletWithNoteIntent,
        compiler=CreateTupletWithNoteCompiler(),
    )
    registry.register(
        intent_type=CreateTupletWithRestIntent,
        compiler=CreateTupletWithRestCompiler(),
    )
    registry.register(intent_type=DeleteBatchIntent, compiler=DeleteBatchCompiler())
    registry.register(intent_type=SetStemIntent, compiler=SetStemCompiler())
    registry.register(intent_type=ResetStemIntent, compiler=ResetStemCompiler())

    return registry


def build_compiler() -> MutationCompiler:
    return MutationCompiler(registry=_build_registry())
