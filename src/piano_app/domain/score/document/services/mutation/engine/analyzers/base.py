from collections.abc import Generator
from typing import Protocol

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class MutationAnalyzer[R: MutationRequest](Protocol):
    """Decomposes one request into work items, yielded one at a time.

    An analyzer may yield further requests (recursive decomposition on *other*
    entities) that its request's axis admits — its own or a lower one, never across
    contexts and rhythm; a request without an axis is held to its nearest ancestor's —
    and one terminal action on *its own* entity. The engine executes each yielded item —
    a request with its whole subtree — before resuming the analyzer and sends back what
    it produced, so the analyzer continues against the live document. The yield order is
    the execution order. ``geometry`` is the transaction's own, and the index layer marks it
    stale as the journal records each change, so it may be read after a yield; the spans
    and points it returns are snapshots and are not carried across one. To abort the whole
    gesture, raise ``MutationRejectedError``. Yielding nothing is a legitimate no-op.

    An analyzer returns nothing: a create request sends back its terminal's result, so a
    create analyzer always yields its terminal.
    """

    def analyze(
        self,
        *,
        request: R,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis: ...


class PitchAnalyzer[R: MutationRequest](Protocol):
    """An analyzer that also reads the transaction's pitch index.

    Everything said of ``MutationAnalyzer`` holds. ``pitch`` is the transaction's own, like
    ``geometry``, and the index layer keeps it current the same way.
    """

    def analyze(
        self,
        *,
        request: R,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis: ...


class ContextAnalyzer[R: MutationRequest](Protocol):
    """An analyzer that also reads the transaction's context index.

    Everything said of ``MutationAnalyzer`` holds. ``contexts`` is the transaction's own, like
    ``geometry``, and the index layer keeps it current the same way.
    """

    def analyze(
        self,
        *,
        request: R,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> MutationAnalysis: ...


def expect_sent[E: ScoreEntity](*, sent: ScoreEntity | None, expected: type[E]) -> E:
    """What a yielded create sent back, narrowed to the entity type its request creates.

    The send type of an analysis is shared by every item it yields, so the entity is
    narrowed where it is received; anything else is a broken engine contract.
    """
    if not isinstance(sent, expected):
        raise TypeError(
            f"Expected {expected.__name__} to be sent back, "
            f"got {type(sent).__name__ if sent is not None else 'nothing'}."
        )

    return sent


def find_or_create_anchor(
    *,
    measure: Measure,
    position: MeasurePosition,
) -> Generator[MutationWorkItem, ScoreEntity | None, TemporalAnchor]:
    """The anchor at a measure position, created when there is none; to be used as
    ``anchor = yield from find_or_create_anchor(...)``."""
    anchor: TemporalAnchor | None = find_anchor_at(measure=measure, position=position)
    if anchor is None:
        anchor = expect_sent(
            sent=(yield CreateTemporalAnchorRequest(measure=measure, position=position)),
            expected=TemporalAnchor,
        )

    return anchor
