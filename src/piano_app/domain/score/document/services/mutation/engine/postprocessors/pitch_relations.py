from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .base import PitchPostprocessor


class PitchRelationsPostprocessor(PitchPostprocessor):
    """What a gesture may leave behind about pitch, judged once it is over.

    A tie whose notes no longer sound the same is deleted. A chord holding two noteheads of
    one sounding pitch refuses the whole gesture. A note whose pitch cannot be resolved — no
    clef in force — is a broken state and raises ``PitchResolutionError``.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> Sequence[MutationRequest]:
        ties: list[Tie] = []
        for voice in document.voices:
            for leaf in iter_leaves(voice):
                carrier = leaf.carrier
                if not isinstance(carrier, NoteCarrier):
                    continue

                sounding: set[int] = set()
                for note in carrier.notes:
                    midi_note: int = pitch.pitch_of(note=note).midi_note
                    if midi_note in sounding:
                        raise MutationRejectedError("A chord cannot hold one pitch twice.")

                    sounding.add(midi_note)

                    for relation in note.relations:
                        if isinstance(relation, Tie) and not any(
                            relation is other for other in ties
                        ):
                            ties.append(relation)

        fixes: list[MutationRequest] = []
        for tie in ties:
            if pitch.pitch_of(note=tie.start).midi_note != pitch.pitch_of(note=tie.end).midi_note:
                fixes.append(DeleteRequest(target=tie))

        return fixes
