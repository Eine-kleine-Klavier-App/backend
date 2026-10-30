from piano_app.domain.score.document.models.material import CarrierOwner
from piano_app.domain.score.document.models.relations.start_end import NoteToNoteRelation
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import is_touching
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    UpdateRelationStartAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    UpdateRelationStartRequest,
)


class UpdateRelationStartAnalyzer:
    """Moves a note-to-note relation's start; the relation refuses a start it cannot take."""

    def analyze(
        self,
        *,
        request: UpdateRelationStartRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield UpdateRelationStartAction(target=request.target, start_note=request.start_note)


def is_separated(*, geometry: ScoreGeometry, relation: NoteToNoteRelation) -> bool:
    """True when the relation's notes are not neighbours (relation-guard). A relation with a
    grace note is not judged: a grace note has no place of its own on the timeline."""
    start_leaf: CarrierOwner = relation.start.note_carrier.owner
    end_leaf: CarrierOwner = relation.end.note_carrier.owner
    if not isinstance(start_leaf, LeafRhythmicContainer) or not isinstance(
        end_leaf,
        LeafRhythmicContainer,
    ):
        return False

    return not is_touching(geometry=geometry, first=start_leaf, second=end_leaf)
