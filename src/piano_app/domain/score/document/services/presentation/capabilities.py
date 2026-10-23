from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, Slur
from piano_app.domain.score.document.models.material import Carrier, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.presentation import PresentationTarget, ReferencePoint
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer


@dataclass(frozen=True, slots=True, kw_only=True)
class PlacementCapabilities:
    vertical: bool = False
    endpoints: bool = False
    directed: bool = False
    horizontal: bool = False
    horizontal_endpoints: bool = False
    # the vertical and endpoint values are factors of the automatic size, so above zero; not
    # scaled, they are fractions of the target's frame
    scaled: bool = False


def presentation_capabilities(
    *, document: ScoreDocument
) -> dict[PresentationTarget, PlacementCapabilities]:
    result: dict[PresentationTarget, PlacementCapabilities] = {}
    for measure in document.measures:
        for anchor in measure.anchors:
            for context in anchor.starting_contexts:
                if isinstance(context, Context):
                    result[PresentationTarget(entity_id=context.id)] = PlacementCapabilities(
                        vertical=True,
                        endpoints=isinstance(context, Slur),
                        scaled=not isinstance(context, Slur),
                    )
                if isinstance(context, Slur):
                    result[
                        PresentationTarget(entity_id=context.id, reference=ReferencePoint.HEIGHT)
                    ] = PlacementCapabilities(vertical=True, scaled=True)
                    result[
                        PresentationTarget(
                            entity_id=context.id, reference=ReferencePoint.LOWER_EDGE
                        )
                    ] = PlacementCapabilities(
                        vertical=True,
                        endpoints=True,
                        horizontal=True,
                        horizontal_endpoints=True,
                    )
            carriers: list[Carrier | None] = []
            for container in anchor.containers:
                if not isinstance(container, LeafRhythmicContainer):
                    continue
                carriers.append(container.carrier)
                for group in (container.grace_before, container.grace_after):
                    if group is not None:
                        carriers.extend(item.carrier for item in group.grace_items)
            for carrier in carriers:
                if isinstance(carrier, RestCarrier) and carrier.rest is not None:
                    result[PresentationTarget(entity_id=carrier.id)] = PlacementCapabilities(
                        vertical=True
                    )
                if isinstance(carrier, NoteCarrier):
                    result[
                        PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
                    ] = PlacementCapabilities(vertical=True, directed=True, scaled=True)
                if carrier is None:
                    continue
                for relation in carrier.carrier_group_relations:
                    if isinstance(relation, Beam):
                        result[PresentationTarget(entity_id=relation.id)] = PlacementCapabilities(
                            endpoints=True, scaled=True
                        )
    return result
