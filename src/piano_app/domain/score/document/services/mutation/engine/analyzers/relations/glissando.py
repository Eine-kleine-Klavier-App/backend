from piano_app.domain.score.document.models.material import CarrierOwner, Note
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import is_touching
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations.relation import (
    is_separated,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateGlissandoAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateGlissandoRequest,
)


def check_glissando(*, relation: Glissando, geometry: ScoreGeometry) -> MutationAnalysis:
    """Removes a glissando whose notes are no longer neighbours (relation-guard).

    Decided before the first yield, on the live document.
    """
    if is_separated(geometry=geometry, relation=relation):
        yield DeleteRequest(target=relation)


class CreateGlissandoAnalyzer:
    """Decides whether two metric notes may be connected by a glissando.

    The notes must touch in one voice, the first note starts no other glissando, and the notes
    differ: a glissando between a step and itself goes nowhere.
    """

    def analyze(
        self,
        *,
        request: CreateGlissandoRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        start_note: Note = request.start_note
        end_note: Note = request.end_note

        if start_note is end_note or (
            start_note.staff is end_note.staff and start_note.staff_step == end_note.staff_step
        ):
            raise MutationRejectedError("A glissando joins two different steps.")

        if any(
            isinstance(relation, Glissando) and relation.start is start_note
            for relation in start_note.relations
        ):
            raise MutationRejectedError("Note already starts another glissando.")

        start_leaf: CarrierOwner = start_note.note_carrier.owner
        end_leaf: CarrierOwner = end_note.note_carrier.owner
        if not isinstance(start_leaf, LeafRhythmicContainer) or not isinstance(
            end_leaf,
            LeafRhythmicContainer,
        ):
            raise MutationRejectedError("Glissandos involving grace notes are not yet supported.")

        if not is_touching(geometry=geometry, first=start_leaf, second=end_leaf):
            raise MutationRejectedError("Glissando notes must touch in one voice.")

        yield CreateGlissandoAction(
            start_note=start_note,
            end_note=end_note,
            glissando_type=request.glissando_type,
        )
