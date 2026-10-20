from dataclasses import dataclass
from enum import StrEnum


class ReferencePoint(StrEnum):
    # a context, a rest or a beam as a whole; a slur's top edge
    BODY = "body"
    # a stem's tip: a factor of its automatic length
    STEM_TIP = "stem_tip"
    LOWER_EDGE = "lower_edge"
    # a slur's arch height: a factor of its automatic height (1 = as automatic)
    HEIGHT = "height"


@dataclass(frozen=True, slots=True, kw_only=True)
class PresentationTarget:
    entity_id: str
    reference: ReferencePoint = ReferencePoint.BODY
