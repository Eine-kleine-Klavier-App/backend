from collections.abc import Sequence

from piano_app.application.errors import (
    DraftNotFoundError,
    DraftVersionConflictError,
    ScoreEditRejectedError,
)
from piano_app.application.ports import DraftHistory
from piano_app.application.ports.score import (
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    RecordStep,
    VersionedDraftDocument,
)
from piano_app.application.use_cases.score.shared import (
    ScoreState,
    ScoreView,
    require_accessible_draft,
)
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation import MutationCompiler, MutationEngine
from piano_app.domain.score.document.services.mutation.compiler import EditIntent
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.presentation import (
    PresentationCommand,
    PresentationEditor,
)


class ScoreEditService:
    """Application orchestration for editing a transient score draft.

    Runs edits through the domain mutation engine, keyed by draft id (the
    working copy — see ``DraftHistory``). The current outbound adapter is
    in-memory; a cache-backed adapter can replace it without changing this use
    case. Persisting a finished draft is a separate future application use case.
    """

    def __init__(
        self,
        *,
        engine: MutationEngine,
        compiler: MutationCompiler,
        history: DraftHistory,
    ) -> None:
        self._engine: MutationEngine = engine
        self._compiler: MutationCompiler = compiler
        self._drafts_history: DraftHistory = history

    async def apply(
        self,
        *,
        draft_id: str,
        actor_id: str,
        intent: EditIntent,
        presentation: Sequence[PresentationCommand] = (),
    ) -> ScoreState:
        """Runs one edit intent against the draft as one gesture and commits it. The presentation
        commands, if any, are part of the gesture: they are applied in the same transaction, so a
        refusal of either leaves the draft as it was and one undo takes both back."""
        versioned: VersionedDraftDocument = await self._load(draft_id=draft_id, actor_id=actor_id)
        document: ScoreDocument = versioned.document
        entities: EntityIndex = EntityIndex(document=document)
        try:
            requests: Sequence[MutationRequest] = self._compiler.compile(
                document=document,
                intent=intent,
                entities=entities,
            )
            self._run(
                document=document,
                entities=entities,
                requests=requests,
                presentation=presentation,
            )
        except MutationRejectedError as error:
            raise ScoreEditRejectedError(reason=error.reason) from error

        step: RecordStep = await self._commit(versioned=versioned)
        return ScoreState(
            document=document, view=ScoreView(document=document), version=step.to_version, step=step
        )

    async def apply_presentation(
        self, *, draft_id: str, actor_id: str, commands: Sequence[PresentationCommand]
    ) -> ScoreState:
        versioned = await self._load(draft_id=draft_id, actor_id=actor_id)
        log = MutationLog()
        try:
            PresentationEditor().apply(document=versioned.document, commands=commands, sink=log)
        except ValueError as error:
            log.rollback()
            raise ScoreEditRejectedError(reason=str(error)) from error
        step: RecordStep = (
            await self._commit(versioned=versioned)
            if log.has_changes
            else self._unchanged(versioned=versioned)
        )
        return ScoreState(
            document=versioned.document,
            view=ScoreView(document=versioned.document),
            version=step.to_version,
            step=step,
        )

    async def undo(
        self,
        *,
        draft_id: str,
        actor_id: str,
    ) -> ScoreState:
        # An empty history is a successful no-op, not an error: the request was
        # understood and the draft is left in a valid state.
        # Return the current view either way
        versioned: VersionedDraftDocument = await self._load(draft_id=draft_id, actor_id=actor_id)

        try:
            step: RecordStep | None = await self._drafts_history.undo(draft=versioned)
        except DraftStoreNotFoundError as error:
            raise DraftNotFoundError(draft_id=error.draft_id) from error
        except DraftStoreVersionConflictError as error:
            raise DraftVersionConflictError(
                draft_id=error.draft_id, version=error.version
            ) from error

        current: VersionedDraftDocument = await self._load(draft_id=draft_id, actor_id=actor_id)
        return ScoreState(
            document=current.document,
            view=ScoreView(document=current.document),
            version=current.version,
            step=step if step is not None else self._unchanged(versioned=versioned),
        )

    async def redo(
        self,
        *,
        draft_id: str,
        actor_id: str,
    ) -> ScoreState:
        versioned: VersionedDraftDocument = await self._load(draft_id=draft_id, actor_id=actor_id)

        try:
            step = await self._drafts_history.redo(draft=versioned)
        except DraftStoreNotFoundError as error:
            raise DraftNotFoundError(draft_id=error.draft_id) from error
        except DraftStoreVersionConflictError as error:
            raise DraftVersionConflictError(
                draft_id=error.draft_id, version=error.version
            ) from error

        current: VersionedDraftDocument = await self._load(draft_id=draft_id, actor_id=actor_id)
        return ScoreState(
            document=current.document,
            view=ScoreView(document=current.document),
            version=current.version,
            step=step if step is not None else self._unchanged(versioned=versioned),
        )

    async def _load(self, *, draft_id: str, actor_id: str) -> VersionedDraftDocument:
        return await require_accessible_draft(
            storage=self._drafts_history, draft_id=draft_id, viewer_id=actor_id
        )

    def _unchanged(self, *, versioned: VersionedDraftDocument) -> RecordStep:
        """The step of a request that changed nothing: the draft stays at its version."""
        return RecordStep(
            before=versioned.stored.record,
            change={},
            from_version=versioned.version,
            to_version=versioned.version,
        )

    async def _commit(
        self,
        *,
        versioned: VersionedDraftDocument,
    ) -> RecordStep:
        try:
            return await self._drafts_history.commit(draft=versioned)
        except DraftStoreNotFoundError as error:
            raise DraftNotFoundError(draft_id=error.draft_id) from error
        except DraftStoreVersionConflictError as error:
            raise DraftVersionConflictError(
                draft_id=error.draft_id, version=error.version
            ) from error

    # TODO consider moving commit here
    def _run(
        self,
        *,
        document: ScoreDocument,
        entities: EntityIndex,
        requests: Sequence[MutationRequest],
        presentation: Sequence[PresentationCommand] = (),
    ) -> None:
        with self._engine.transaction(document=document, entities=entities) as transaction:
            transaction.run(requests=requests)
            if transaction.log.has_changes:
                document.renew_music_revision(sink=transaction.log)
            if presentation:
                try:
                    PresentationEditor().apply(
                        document=document, commands=presentation, sink=transaction.log
                    )
                except ValueError as error:
                    raise MutationRejectedError(reason=str(error)) from error
            PresentationEditor().prune(document=document, sink=transaction.log)
