from fractions import Fraction

from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Fingering
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.engine.indexes import Indexes
from piano_app.domain.score.document.services.mutation.engine.registry import (
    MutationAnalyzerRegistry,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateFingeringRequest,
    UpdateStaffStepRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class _Plain:
    def __init__(self, *, seen: list[tuple[str, object]]) -> None:
        self._seen: list[tuple[str, object]] = seen

    def analyze(
        self, *, request: UpdateFingeringRequest, geometry: ScoreGeometry
    ) -> MutationAnalysis:
        self._seen.append(("geometry", geometry))
        yield from ()


class _Pitched:
    def __init__(self, *, seen: list[tuple[str, object]]) -> None:
        self._seen: list[tuple[str, object]] = seen

    def analyze(
        self, *, request: UpdateStaffStepRequest, geometry: ScoreGeometry, pitch: ScorePitch
    ) -> MutationAnalysis:
        self._seen.append(("geometry", geometry))
        self._seen.append(("pitch", pitch))
        yield from ()


class _Contextual:
    def __init__(self, *, seen: list[tuple[str, object]]) -> None:
        self._seen: list[tuple[str, object]] = seen

    def analyze(
        self, *, request: UpdateFingeringRequest, geometry: ScoreGeometry, contexts: ContextIndex
    ) -> MutationAnalysis:
        self._seen.append(("geometry", geometry))
        self._seen.append(("contexts", contexts))
        yield from ()


def _indexes(*, document: ScoreDocument) -> Indexes:
    geometry: ScoreGeometry = ScoreGeometry(document=document)

    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)

    return Indexes(
        entities=EntityIndex(document=document),
        geometry=geometry,
        pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
        contexts=contexts,
    )


def test_each_analyzer_is_handed_only_the_indexes_it_reads() -> None:
    document: ScoreDocument = score()
    target: Note = note(document, Fraction(0))
    indexes: Indexes = _indexes(document=document)
    seen: list[tuple[str, object]] = []
    registry: MutationAnalyzerRegistry = MutationAnalyzerRegistry()
    registry.register(request_type=UpdateFingeringRequest, analyzer=_Plain(seen=seen))
    registry.register_pitch(request_type=UpdateStaffStepRequest, analyzer=_Pitched(seen=seen))

    list(
        registry.analyze(
            request=UpdateFingeringRequest(target=target, fingering=Fingering.NONE),
            indexes=indexes,
        )
    )
    assert seen == [("geometry", indexes.geometry)]

    seen.clear()
    list(
        registry.analyze(
            request=UpdateStaffStepRequest(target=target, staff_step=1), indexes=indexes
        )
    )
    assert seen == [("geometry", indexes.geometry), ("pitch", indexes.pitch)]


def test_an_analyzer_registered_for_contexts_is_handed_the_context_index() -> None:
    document: ScoreDocument = score()
    target: Note = note(document, Fraction(0))
    indexes: Indexes = _indexes(document=document)
    seen: list[tuple[str, object]] = []
    registry: MutationAnalyzerRegistry = MutationAnalyzerRegistry()
    registry.register_contexts(request_type=UpdateFingeringRequest, analyzer=_Contextual(seen=seen))

    list(
        registry.analyze(
            request=UpdateFingeringRequest(target=target, fingering=Fingering.NONE),
            indexes=indexes,
        )
    )

    assert seen == [("geometry", indexes.geometry), ("contexts", indexes.contexts)]
