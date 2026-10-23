from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .hierarchy_traversal import voice_of


def is_touching(
    *,
    geometry: ScoreGeometry,
    first: LeafRhythmicContainer,
    second: LeafRhythmicContainer,
) -> bool:
    """True when ``second`` follows ``first`` in one voice with no time between them: the
    end of the first is the start of the second on the global timeline.

    Neighbours are geometry, not the presence of an element: any empty time between the two,
    a sleeping measure too, keeps them apart.
    """
    if voice_of(first) is not voice_of(second):
        return False

    return (
        geometry.global_span_of(container=first).end
        == geometry.global_span_of(container=second).start
    )
