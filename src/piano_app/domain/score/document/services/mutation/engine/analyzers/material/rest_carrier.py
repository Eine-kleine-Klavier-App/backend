from collections.abc import Sequence

from piano_app.domain.score.document.models.material import Rest, RestCarrier
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateRestCarrierAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateRestCarrierRequest,
)


class CreateRestCarrierAnalyzer:
    """Creates a rest carrier on the leaf or grace item its request names; the leaf and its room
    are decided above, by the spans, and the owner itself refuses a second carrier."""

    def analyze(
        self,
        *,
        request: CreateRestCarrierRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield CreateRestCarrierAction(
            owner=request.owner,
        )


def cascade_rest_carrier(*, target: RestCarrier) -> Sequence[Deletable]:
    """Decides the rest carrier's deletion cascade.

    A group relation is deleted only when it cannot remain valid without this
    carrier; surviving groups lose the carrier during its detach. The optional
    rest is deleted before the carrier. Owner cleanup is deferred to the boundary.
    """
    # decided before the first deletion: each relation's deletion removes it from the
    # carrier's own list
    doomed: list[Deletable] = []
    for relation in target.carrier_group_relations:
        if not relation.can_remove_carrier(carrier=target):
            doomed.append(relation)

    rest: Rest | None = target.rest
    if rest is not None:
        doomed.append(rest)

    return doomed
