from typing import Any

from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    ContextAnalyzer,
    MutationAnalyzer,
    PitchAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.handlers import MutationHandler
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationAction,
    MutationRequest,
)

from .indexes import Indexes


class MutationAnalyzerRegistry:
    """Maps a concrete request type to the analyzer that is responsible for it.

    An analyzer registered with ``register_pitch`` is also handed the transaction's pitch
    index, one registered with ``register_contexts`` its context index; the others never see
    them.
    """

    def __init__(self) -> None:
        self._analyzers: dict[type[MutationRequest], MutationAnalyzer[Any]] = {}
        self._pitch_analyzers: dict[type[MutationRequest], PitchAnalyzer[Any]] = {}
        self._context_analyzers: dict[type[MutationRequest], ContextAnalyzer[Any]] = {}

    def register[R: MutationRequest](
        self,
        *,
        request_type: type[R],
        analyzer: MutationAnalyzer[R],
    ) -> None:
        self._analyzers[request_type] = analyzer

    def register_pitch[R: MutationRequest](
        self,
        *,
        request_type: type[R],
        analyzer: PitchAnalyzer[R],
    ) -> None:
        self._pitch_analyzers[request_type] = analyzer

    def register_contexts[R: MutationRequest](
        self,
        *,
        request_type: type[R],
        analyzer: ContextAnalyzer[R],
    ) -> None:
        self._context_analyzers[request_type] = analyzer

    def analyze(
        self,
        *,
        request: MutationRequest,
        indexes: Indexes,
    ) -> MutationAnalysis:
        """Runs the request's analyzer, a generator, with what it takes."""
        pitch_analyzer: PitchAnalyzer[Any] | None = self._pitch_analyzers.get(type(request))
        if pitch_analyzer is not None:
            return pitch_analyzer.analyze(
                request=request, geometry=indexes.geometry, pitch=indexes.pitch
            )

        context_analyzer: ContextAnalyzer[Any] | None = self._context_analyzers.get(type(request))
        if context_analyzer is not None:
            return context_analyzer.analyze(
                request=request, geometry=indexes.geometry, contexts=indexes.contexts
            )

        return self._analyzers[type(request)].analyze(request=request, geometry=indexes.geometry)


class MutationHandlerRegistry:
    """Maps a concrete action type to the handler that executes it."""

    def __init__(self) -> None:
        self._handlers: dict[type[MutationAction], MutationHandler[Any]] = {}

    def register[A: MutationAction](
        self,
        *,
        action_type: type[A],
        handler: MutationHandler[A],
    ) -> None:
        self._handlers[action_type] = handler

    def get[A: MutationAction](self, *, action_type: type[A]) -> MutationHandler[A]:
        return self._handlers[action_type]
