from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CheckRelationRequest,
)


class RelationGuard:
    """Checks every relation of the document (relation-guard): each relation kind's rules
    live in its own check, so no analyzer repairs a relation it breaks.

    Every relation on the score's metric elements is checked once, in document order — by
    voice, then by the leaf it is first reached from.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[CheckRelationRequest]:
        relations: list[Relation] = []
        for voice in document.voices:
            for leaf in iter_leaves(voice):
                carrier: Carrier | None = leaf.carrier
                if carrier is None:
                    continue

                found: list[Relation] = [*carrier.carrier_group_relations]
                if isinstance(carrier, NoteCarrier):
                    for note in carrier.notes:
                        found.extend(note.relations)

                for relation in found:
                    if not any(relation is listed for listed in relations):
                        relations.append(relation)

        return [CheckRelationRequest(relation=relation) for relation in relations]
