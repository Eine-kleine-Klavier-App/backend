from piano_app.adapters.outbound.in_memory.draft_storage import InMemoryDraftStorage
from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService


def in_memory_history(*, max_history_size: int = 30) -> DraftHistoryService:
    """Drafts with undo and redo kept in process, the way the app runs without Redis."""
    return DraftHistoryService(
        storage=InMemoryDraftStorage(),
        codec=ScoreDocumentCodec(),
        max_history_size=max_history_size,
    )
