from collections.abc import Callable, Sequence

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.material import (
    cascade_note,
    cascade_note_carrier,
    cascade_rest_carrier,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    cascade_grace_group,
    cascade_grace_item,
    cascade_group,
    cascade_leaf,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.temporal import (
    cascade_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    DeleteContextAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    DeleteNoteAction,
    DeleteNoteCarrierAction,
    DeleteRestAction,
    DeleteRestCarrierAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    DeleteRelationAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    DeleteGraceGroupAction,
    DeleteGraceItemAction,
    DeleteLeafAction,
    DeleteRhythmicGroupAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    DeleteTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
    DeleteRequest,
)

# What goes before each kind of entity, and the action that removes it. An entity that owns
# nothing has no cascade. A new kind is added here.
_KINDS: dict[
    type[ScoreEntity],
    tuple[Callable[..., Sequence[Deletable]] | None, Callable[..., MutationWorkItem]],
] = {
    Note: (cascade_note, DeleteNoteAction),
    NoteCarrier: (cascade_note_carrier, DeleteNoteCarrierAction),
    Rest: (None, DeleteRestAction),
    RestCarrier: (cascade_rest_carrier, DeleteRestCarrierAction),
    LeafRhythmicContainer: (cascade_leaf, DeleteLeafAction),
    GraceGroup: (cascade_grace_group, DeleteGraceGroupAction),
    GraceItem: (cascade_grace_item, DeleteGraceItemAction),
    GroupRhythmicContainer: (cascade_group, DeleteRhythmicGroupAction),
    TemporalAnchor: (cascade_anchor, DeleteTemporalAnchorAction),
    Relation: (None, DeleteRelationAction),
    Context: (None, DeleteContextAction),
}


class DeleteAnalyzer:
    """Deletes an entity after everything that must not outlive it (deletion-cascade).

    What goes first is decided by the kind of the entity, before the first yield, on the
    live document; each of those is deleted by this same request, then the entity itself.
    """

    def analyze(
        self,
        *,
        request: DeleteRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        target: Deletable = request.target

        for kind, (cascade, action) in _KINDS.items():
            if isinstance(target, kind):
                if cascade is not None:
                    for doomed in cascade(target=target):
                        yield DeleteRequest(target=doomed)

                yield action(target=target)

                return

        raise TypeError(f"Unsupported deletion target: {type(target).__name__}.")
