from dataclasses import dataclass

from piano_app.application.errors import ContextNotFoundError
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.services.contexts import ContextIndex, covered_by
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextCoverage:
    """The carriers and the notes a context covers, in timeline order."""

    carrier_ids: tuple[str, ...]
    note_ids: tuple[str, ...]


def context_coverage(*, document: ScoreDocument, context_id: str) -> ContextCoverage:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    for context in contexts.contexts():
        if context.id == context_id:
            coverage = covered_by(
                context=context, document=document, geometry=geometry, contexts=contexts
            )
            return ContextCoverage(
                carrier_ids=tuple(carrier.id for carrier in coverage.carriers),
                note_ids=tuple(note.id for note in coverage.notes),
            )
    raise ContextNotFoundError
