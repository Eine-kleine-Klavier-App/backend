from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Self

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex, IndexLayer
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationAction,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    DeleteMutationRequest,
    UpdateMutationRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .guards import InvariantGuard
from .handlers import MutationHandler
from .indexes import Indexes
from .log import MutationLog
from .postprocessors import MutatedStatePostprocessor, PitchPostprocessor
from .registry import MutationAnalyzerRegistry, MutationHandlerRegistry
from .typing import MutationAnalysis


class MutationEngine:
    """Drains root requests into ordered mutations, executing as it goes.

    Every request is handed to its analyzer, a generator; each item it yields is
    executed **immediately** against the live model — an action by its handler, a
    request by expanding it the same way — and what it produced is sent back before
    the analyzer resumes. So the analyzers' yield order *is* the execution order —
    the engine never reorders. Actions carry live entities: a later item uses what an
    earlier one sent back.

    One intent is one pass: its requests drained, then each postprocessor once, in
    order, each against what the previous one left, then those that read pitch, and last
    the guards, once, against what the posts left. Their fixes are drained as roots and no
    guard judges them again. Passes run in a transaction — one journal, one undo step —
    which rolls every pass back on any error; ``process`` is the transaction of a single
    pass.

    A transaction keeps one geometry, handed to every analyzer, post and guard. The index
    layer marks it stale as the journal records each change, so it always answers for the
    live model. Two hooks let tests compare it with a geometry built from scratch; each is
    called with it and the document when set: ``geometry_check`` once a request that
    executed an action has run its analyzer to the end, ``checkpoint_geometry_check`` after each
    request of a pass, each step an intent request yields and each post, and again once
    the guards have run.

    The transaction keeps one pitch index over that geometry, handed to the analyzers that
    read it (``PitchAnalyzer``) and kept current the same way. ``checkpoint_pitch_check`` is called
    with it, the geometry and the document at the same points as ``checkpoint_geometry_check``,
    to compare it with an index built from scratch.
    """

    def __init__(
        self,
        *,
        handler_registry: MutationHandlerRegistry,
        analyzer_registry: MutationAnalyzerRegistry,
        postprocessors: list[MutatedStatePostprocessor],
        guards: list[InvariantGuard],
        pitch_postprocessors: list[PitchPostprocessor] | None = None,
        geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = None,
        checkpoint_geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = None,
        checkpoint_pitch_check: Callable[[ScorePitch, ScoreGeometry, ScoreDocument], None]
        | None = None,
        checkpoint_entities_check: Callable[[EntityIndex, ScoreDocument], None] | None = None,
    ) -> None:
        self._handler_registry: MutationHandlerRegistry = handler_registry
        self._analyzer_registry: MutationAnalyzerRegistry = analyzer_registry
        self._postprocessors: list[MutatedStatePostprocessor] = postprocessors
        self._guards: list[InvariantGuard] = guards
        self._pitch_postprocessors: list[PitchPostprocessor] = pitch_postprocessors or []
        self._geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = geometry_check
        self._checkpoint_geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = (
            checkpoint_geometry_check
        )
        self._checkpoint_pitch_check: (
            Callable[[ScorePitch, ScoreGeometry, ScoreDocument], None] | None
        ) = checkpoint_pitch_check
        self._checkpoint_entities_check: Callable[[EntityIndex, ScoreDocument], None] | None = (
            checkpoint_entities_check
        )

    def process(
        self, *, document: ScoreDocument, requests: Sequence[MutationRequest]
    ) -> MutationLog:
        """Runs the requests of one intent as a transaction of its own."""
        with self.transaction(document=document) as transaction:
            transaction.run(requests=requests)

        return transaction.log

    def transaction(
        self, *, document: ScoreDocument, entities: EntityIndex | None = None
    ) -> MutationTransaction:
        """A transaction over ``document``, to be used as a context manager. ``entities`` is
        the index of the document's entities a caller has been reading before the transaction,
        which the transaction goes on keeping right; without it the transaction makes one."""
        return MutationTransaction(engine=self, document=document, entities=entities)

    def _run_pass(
        self,
        *,
        document: ScoreDocument,
        indexes: Indexes,
        requests: Sequence[MutationRequest],
        log: MutationLog,
    ) -> None:
        """One intent: its requests, then the postprocessors once each, in their order, then
        the pitch postprocessors, and last the guards once.

        No post runs twice: each one leaves nothing an earlier one would act on. The guards
        come last because fill places a rest in a hole before a relation is judged over it.
        """
        for request in requests:
            self._expand(
                request=request,
                ceiling=None,
                document=document,
                indexes=indexes,
                log=log,
            )
            self._check_indexes(document=document, indexes=indexes)

        for postprocessor in self._postprocessors:
            self._drain(
                requests=postprocessor.search_fixes(document=document, geometry=indexes.geometry),
                document=document,
                indexes=indexes,
                log=log,
            )
            self._check_indexes(document=document, indexes=indexes)

        for pitch_postprocessor in self._pitch_postprocessors:
            self._drain(
                requests=pitch_postprocessor.search_fixes(
                    document=document, geometry=indexes.geometry, pitch=indexes.pitch
                ),
                document=document,
                indexes=indexes,
                log=log,
            )

        self._guard(document=document, indexes=indexes, log=log)

    def _guard(
        self,
        *,
        document: ScoreDocument,
        indexes: Indexes,
        log: MutationLog,
    ) -> None:
        """The end of a pass: each guard's fixes, found against what the previous one left,
        then the index checks.

        Fixes are drained as roots below INTENT, so no guard judges them again.
        """
        for guard in self._guards:
            self._drain(
                requests=guard.search_fixes(document=document, geometry=indexes.geometry),
                document=document,
                indexes=indexes,
                log=log,
            )

        self._check_indexes(document=document, indexes=indexes)

    def _check_indexes(
        self,
        *,
        document: ScoreDocument,
        indexes: Indexes,
    ) -> None:
        """The test hooks that compare the live indexes with ones built from scratch."""
        if self._checkpoint_geometry_check is not None:
            self._checkpoint_geometry_check(indexes.geometry, document)

        if self._checkpoint_pitch_check is not None:
            self._checkpoint_pitch_check(indexes.pitch, indexes.geometry, document)

        if self._checkpoint_entities_check is not None:
            self._checkpoint_entities_check(indexes.entities, document)

    def _drain(
        self,
        *,
        requests: Sequence[MutationRequest],
        document: ScoreDocument,
        indexes: Indexes,
        log: MutationLog,
    ) -> None:
        """Expands each request in turn; one finishes its whole subtree before the next."""
        for request in requests:
            self._expand(
                request=request,
                ceiling=None,
                document=document,
                indexes=indexes,
                log=log,
            )

    def _expand(
        self,
        *,
        request: MutationRequest,
        ceiling: Axis | None,
        document: ScoreDocument,
        indexes: Indexes,
        log: MutationLog,
    ) -> ScoreEntity | None:
        """Drives the request's analyzer and returns what the request sends back.

        Each yielded item is executed at once — a request through its own analyzer, depth
        first — and its result is sent back before the analyzer resumes. A yielded request
        may not rank above the yielding one's axis, nor cross between contexts and rhythm;
        a request without an axis (anchors) may be yielded from anywhere and is held to
        ``ceiling``, its nearest axis-bearing ancestor's axis, so it opens no upward path.
        After each step an intent request yields, once its subtree has executed, the index
        hooks run; no guard does. The only action an analyzer may yield is one terminal of
        its request's own kind (create, delete or update) — a delete or update on its
        request's ``target``: any other action would bypass that entity's analyzer.

        A create request sends back its terminal's result, so it must yield one, of the type
        its request ``creates``: a create action of another entity type is not its terminal.
        """
        analysis: MutationAnalysis = self._analyzer_registry.analyze(
            request=request,
            indexes=indexes,
        )
        axis: Axis | None = request.axis if request.axis is not None else ceiling

        terminal_executed: bool = False
        terminal_produced: ScoreEntity | None = None
        produced: ScoreEntity | None = None

        # closed on every exit, so a suspended analyzer's cleanup runs before the gesture
        # is rolled back rather than whenever the generator is collected
        try:
            while True:
                try:
                    # the yield type is only declared: an analyzer's items are checked here
                    item: object = analysis.send(produced)
                except StopIteration:
                    break

                if isinstance(item, MutationRequest):
                    item_axis: Axis | None = item.axis
                    if axis is not None and item_axis is not None:
                        culprit_axes: str = (
                            f"{type(request).__name__} "
                            f"({axis.name}{'' if request.axis is not None else ', inherited'}) "
                            f"yielded {type(item).__name__} ({item_axis.name})"
                        )

                        # intent tops every axis; contexts and rhythm share no rank
                        if axis is not Axis.INTENT and (axis is Axis.CONTEXTS) != (
                            item_axis is Axis.CONTEXTS
                        ):
                            raise ValueError(
                                f"{culprit_axes}, across contexts and rhythm, which share no rank."
                            )

                        if item_axis < axis:
                            raise ValueError(f"{culprit_axes}, whose axis ranks higher.")

                    produced = self._expand(
                        request=item,
                        ceiling=axis,
                        document=document,
                        indexes=indexes,
                        log=log,
                    )
                    if request.axis is Axis.INTENT:
                        self._check_indexes(document=document, indexes=indexes)

                    continue

                culprit: str = f"{type(request).__name__} yielded {type(item).__name__}"

                if not isinstance(item, MutationAction):
                    raise TypeError(f"{culprit}, which is neither a request nor an action.")

                if terminal_executed:
                    raise ValueError(
                        f"{culprit}: an analyzer may emit only one action — its request's terminal."
                    )

                if (
                    isinstance(item, DeleteMutationAction)
                    and isinstance(request, DeleteMutationRequest)
                ) or (
                    isinstance(item, UpdateMutationAction)
                    and isinstance(request, UpdateMutationRequest)
                ):
                    if item.target is not request.target:
                        raise ValueError(
                            f"{culprit}, which does not target its request's entity "
                            "(target mismatch)."
                        )

                # a create names no entity before it exists: what its request sends back is
                # checked against what it produced once the analyzer ends
                elif not (
                    isinstance(item, CreateMutationAction)
                    and isinstance(request, CreateMutationRequest)
                ):
                    raise ValueError(
                        f"{culprit}, whose kind (create/delete/update) does not match its request."
                    )

                produced = self._execute(action=item, sink=log)
                terminal_executed = True
                terminal_produced = produced

        finally:
            analysis.close()

        if terminal_executed and self._geometry_check is not None:
            self._geometry_check(indexes.geometry, document)

        if isinstance(request, CreateMutationRequest):
            if not terminal_executed:
                raise ValueError(
                    f"{type(request).__name__} was expanded without its terminal action "
                    "(it would send back nothing)."
                )

            if not isinstance(terminal_produced, request.creates):
                raise ValueError(
                    f"{type(request).__name__} sends back {type(terminal_produced).__name__}, "
                    f"not the {request.creates.__name__} it creates."
                )

        return terminal_produced

    def _execute(self, *, action: MutationAction, sink: MutationSink) -> ScoreEntity | None:
        """Executes a single action, checks its type, validates the expected output and
        returns what is produced.
        """
        handler: MutationHandler[MutationAction] = self._handler_registry.get(
            action_type=type(action)
        )
        produced: ScoreEntity | None = handler.handle(action=action, sink=sink)

        if isinstance(action, CreateMutationAction):
            if produced is None:
                raise ValueError(f"Create handler produced nothing: {type(action).__name__}.")

        elif isinstance(action, DeleteMutationAction):
            if produced is not None:
                raise ValueError(f"Delete handler produced an entity: {type(action).__name__}.")

        elif isinstance(action, UpdateMutationAction):
            if produced is not None:
                raise ValueError(f"Update handler produced an entity: {type(action).__name__}.")

        else:
            raise ValueError(f"Action is neither create nor delete: {type(action).__name__}.")

        return produced


class MutationTransaction:
    """One transaction over the passes of several intents — one journal, one undo step.

    Used as a context manager, entered once. Each ``run`` is one pass against the
    document the previous pass left. Any exception escaping the block — from a pass, or
    from whatever the caller does between passes, such as compiling the next intent —
    rolls every pass back and re-raises; on success ``log`` journals all of them.
    """

    def __init__(
        self,
        *,
        engine: MutationEngine,
        document: ScoreDocument,
        entities: EntityIndex | None = None,
    ) -> None:
        self._engine: MutationEngine = engine
        self._document: ScoreDocument = document
        # one for every pass: the index layer marks it as the journal records changes, so it
        # stays live
        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        self._indexes: Indexes = Indexes(
            entities=entities if entities is not None else EntityIndex(document=document),
            geometry=geometry,
            pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
            contexts=contexts,
        )
        self._log: MutationLog = MutationLog()
        self._log.subscribe(
            IndexLayer(
                indexes=(
                    self._indexes.entities,
                    self._indexes.geometry,
                    self._indexes.contexts,
                    self._indexes.pitch,
                )
            )
        )
        self._entered: bool = False
        self._open: bool = False

    @property
    def log(self) -> MutationLog:
        return self._log

    @property
    def entities(self) -> EntityIndex:
        return self._indexes.entities

    def __enter__(self) -> Self:
        if self._entered:
            raise RuntimeError("A transaction is entered only once.")

        self._entered = True
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._open = False
        if exc is not None:
            self._log.rollback()

    def run(self, *, requests: Sequence[MutationRequest]) -> None:
        """Runs the requests of one intent as one pass of this transaction."""
        if not self._open:
            raise RuntimeError("A transaction runs a pass only inside its with block.")

        self._engine._run_pass(
            document=self._document,
            indexes=self._indexes,
            requests=requests,
            log=self._log,
        )
