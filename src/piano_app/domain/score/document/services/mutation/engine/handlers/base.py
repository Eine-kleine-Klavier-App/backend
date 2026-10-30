from typing import Protocol

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions import MutationAction


class MutationHandler[A: MutationAction](Protocol):
    """Executes one action type.
    Returns an entity if it was produced, or None if it was not.
    """

    def handle(
        self,
        *,
        action: A,
        sink: MutationSink,
    ) -> ScoreEntity | None: ...
