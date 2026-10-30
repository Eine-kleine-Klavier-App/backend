from collections.abc import Callable

from piano_app.domain.score.document.models.relations import (
    Beam,
    Glissando,
    Relation,
    Tie,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations.beam import (
    check_beam,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations.glissando import (
    check_glissando,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations.tie import (
    check_tie,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CheckRelationRequest,
)

# The rules of each kind of relation live with the kind; a new kind is added here.
_CHECKS: dict[type[Relation], Callable[..., MutationAnalysis]] = {
    Beam: check_beam,
    Glissando: check_glissando,
    Tie: check_tie,
}


class CheckRelationAnalyzer:
    """Judges a relation by the rules of its kind (relation-guard): what holds is left
    alone, what is broken is repaired or removed.

    Decided before the first yield, on the live document.
    """

    def analyze(
        self,
        *,
        request: CheckRelationRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        relation: Relation = request.relation

        for kind, check in _CHECKS.items():
            if isinstance(relation, kind):
                yield from check(relation=relation, geometry=geometry)

                return

        raise TypeError(f"Unsupported relation type: {type(relation).__name__}.")
