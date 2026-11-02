from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain, Volta
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.contexts.repeat_nesting import (
    check_nesting,
    pieces_of_elements,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)


class JumpElementsGuard:
    """Reject a settled mutation that breaks a repeat or a volta, or sets them partly over
    each other: whatever changed the barlines around them, the elements must still hold."""

    def search_fixes(
        self, *, document: ScoreDocument, geometry: ScoreGeometry
    ) -> Sequence[MutationRequest]:
        contexts = ContextIndex(document=document, geometry=geometry)
        refrains: list[Refrain] = contexts.contexts_of(kind=Refrain, scope=Scope.score())
        voltas: list[Volta] = contexts.contexts_of(kind=Volta, scope=Scope.score())
        try:
            for refrain in refrains:
                refrain.validate()

            for volta in voltas:
                volta.validate()

            check_nesting(elements=pieces_of_elements(geometry=geometry, contexts=contexts))
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        return ()
