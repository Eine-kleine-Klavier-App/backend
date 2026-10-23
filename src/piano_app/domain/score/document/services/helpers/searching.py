from collections.abc import Sequence

from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)

# Slot lookup: what already sits at a given place in the model. Purely a question
# about occupancy, not about coordinates -- anything that needs to measure, project
# or compare positions belongs in `services/geometry` instead.


def find_anchor_at(
    *,
    measure: Measure,
    position: MeasurePosition,
) -> TemporalAnchor | None:
    # one or None guaranteed in model
    return next(
        (anchor for anchor in measure.anchors if anchor.position == position),
        None,
    )


def find_beams(*, carriers: Sequence[Carrier]) -> list[Beam]:
    """The beams the carriers belong to, each once, in the order first met."""
    beams: list[Beam] = []
    for carrier in carriers:
        for relation in carrier.carrier_group_relations:
            if isinstance(relation, Beam) and not any(relation is beam for beam in beams):
                beams.append(relation)

    return beams
