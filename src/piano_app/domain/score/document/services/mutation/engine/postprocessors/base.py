from abc import ABC, abstractmethod
from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class MutatedStatePostprocessor(ABC):
    """Postprocessors are intended to guard a per gesture invariants
    which cannot be enforced by the analyzers
    and that should not be precalculated by the compilers.
    """

    @abstractmethod
    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[MutationRequest]: ...


class PitchPostprocessor(ABC):
    """A postprocessor that also reads the transaction's pitch index: it judges what the notes
    sound like once the gesture is over, never while it is half done."""

    @abstractmethod
    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> Sequence[MutationRequest]: ...
