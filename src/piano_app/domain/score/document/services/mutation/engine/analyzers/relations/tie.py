from piano_app.domain.score.document.models.material import CarrierOwner, Note
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import is_touching
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations.relation import (
    is_separated,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateTieAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def check_tie(*, relation: Tie, geometry: ScoreGeometry) -> MutationAnalysis:
    """Removes a tie whose notes are no longer neighbours (relation-guard).

    Decided before the first yield, on the live document.
    """
    if is_separated(geometry=geometry, relation=relation):
        yield DeleteRequest(target=relation)


class CreateTieAnalyzer:
    """Decides whether two metric notes may be connected by a tie.

    The notes must touch in one voice, with the corresponding outgoing and incoming tie
    ends available, and sound the same.
    """

    def analyze(
        self,
        *,
        request: CreateTieRequest,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis:
        start_note: Note = request.start_note
        end_note: Note = request.end_note

        # other ties check
        if any(
            isinstance(relation, Tie) and relation.start is start_note
            for relation in start_note.relations
        ):
            raise MutationRejectedError("Note already starts another tie.")

        if any(
            isinstance(relation, Tie) and relation.end is end_note
            for relation in end_note.relations
        ):
            raise MutationRejectedError("Note already ends another tie.")

        # TODO add support for grace notes
        start_leaf: CarrierOwner = start_note.note_carrier.owner
        end_leaf: CarrierOwner = end_note.note_carrier.owner
        if not isinstance(start_leaf, LeafRhythmicContainer) or not isinstance(
            end_leaf,
            LeafRhythmicContainer,
        ):
            raise MutationRejectedError("Ties involving grace notes are not yet supported.")

        # neighbourhood check
        if not is_touching(geometry=geometry, first=start_leaf, second=end_leaf):
            raise MutationRejectedError("Tied notes must touch in one voice.")

        # a tie joins notes of one sounding pitch
        try:
            sounds_alike: bool = (
                pitch.pitch_of(note=start_note).midi_note == pitch.pitch_of(note=end_note).midi_note
            )
        except PitchResolutionError as error:
            raise MutationRejectedError("The pitch of a tied note cannot be resolved.") from error

        if not sounds_alike:
            raise MutationRejectedError("Tied notes must sound the same.")

        yield CreateTieAction(
            start_note=start_note,
            end_note=end_note,
        )
