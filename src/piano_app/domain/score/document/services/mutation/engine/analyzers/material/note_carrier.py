from collections.abc import Sequence

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import check_articulations
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteCarrierAction,
    UpdateArticulationAction,
    UpdateOrnamentAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    UpdateArticulationRequest,
    UpdateOrnamentRequest,
)


class CreateNoteCarrierAnalyzer:
    """Creates a note carrier on the leaf or grace item its request names; the leaf and its room are
    decided above, by the spans, and the owner itself refuses a second carrier."""

    def analyze(
        self,
        *,
        request: CreateNoteCarrierRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield CreateNoteCarrierAction(
            owner=request.owner,
            articulations=request.articulations,
            ornament=request.ornament,
        )


def cascade_note_carrier(*, target: NoteCarrier) -> Sequence[Deletable]:
    """Decides the note carrier's deletion cascade.

    A group relation is deleted only when it cannot remain valid without this
    carrier; surviving groups lose the carrier during its detach. All notes are
    deleted before the carrier. Cleanup of its owner is deferred to the boundary.
    """
    # decided before the first deletion: each one removes its entity from the carrier's own
    # lists
    doomed: list[Deletable] = []
    for carrier_relation in target.carrier_group_relations:
        if not carrier_relation.can_remove_carrier(carrier=target):
            doomed.append(carrier_relation)

    for note in target.notes:
        doomed.append(note)

    return doomed


class UpdateArticulationAnalyzer:
    """Refuses a set of marks that holds an exclusive pair; nothing else reads the marks to
    decide."""

    def analyze(
        self,
        *,
        request: UpdateArticulationRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        try:
            check_articulations(articulations=request.articulations)
        except ValueError as error:
            raise MutationRejectedError(str(error)) from error

        yield UpdateArticulationAction(target=request.target, articulations=request.articulations)


class UpdateOrnamentAnalyzer:
    """Decides nothing: an ornament guards no invariant of the music, and nothing reads it
    to decide."""

    def analyze(
        self,
        *,
        request: UpdateOrnamentRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield UpdateOrnamentAction(target=request.target, ornament=request.ornament)
