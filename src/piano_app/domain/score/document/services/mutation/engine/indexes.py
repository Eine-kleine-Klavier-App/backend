from dataclasses import dataclass

from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


@dataclass(frozen=True, slots=True, kw_only=True)
class Indexes:
    """The indexes of one transaction, kept current as the journal records changes.

    The engine passes them as one: an analyzer, a post or a guard is handed the ones it
    reads.
    """

    geometry: ScoreGeometry
    pitch: ScorePitch
    contexts: ContextIndex
