"""Live audition orchestration; pitch/dynamics still come from the domain projection."""

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TypeVar

from piano_app.application.errors import (
    PlaybackRejectedError,
    PlaybackUnavailableError,
)
from piano_app.application.ports.playback import AudioChunk, LivePlaybackRenderer, PlaybackSession
from piano_app.application.ports.score import DraftStore
from piano_app.application.use_cases.score.shared.draft_access import require_accessible_draft
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.playback import PlaybackProjection

from .service import preview_projection

_Result = TypeVar("_Result")


class PreviewSessionService:
    def __init__(self, *, storage: DraftStore, renderer: LivePlaybackRenderer | None) -> None:
        self._storage = storage
        self._renderer = renderer
        self._sessions: set[PreviewSession] = set()

    async def open(self, *, draft_id: str, viewer_id: str) -> PreviewSession:
        await require_accessible_draft(
            storage=self._storage, draft_id=draft_id, viewer_id=viewer_id
        )
        if self._renderer is None or len(self._sessions) >= 32:
            raise PlaybackUnavailableError("Live preview is unavailable.")
        session = PreviewSession(
            storage=self._storage,
            renderer=self._renderer,
            draft_id=draft_id,
            viewer_id=viewer_id,
            on_close=self._sessions.discard,
        )
        self._sessions.add(session)
        return session

    async def close(self) -> None:
        await asyncio.gather(*(session.close() for session in tuple(self._sessions)))


class PreviewSession:
    """One connection, one serial native worker and a versioned, bounded projection cache."""

    def __init__(
        self,
        *,
        storage: DraftStore,
        renderer: LivePlaybackRenderer,
        draft_id: str,
        viewer_id: str,
        on_close: Callable[[PreviewSession], None],
    ) -> None:
        self._storage = storage
        self._renderer = renderer
        self._draft_id = draft_id
        self._viewer_id = viewer_id
        self._on_close = on_close
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="piano-preview")
        self._native: PlaybackSession | None = None
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self._sequence = 0
        self._rendered_sequence = 0
        self._music_revision: str | None = None
        self._cache: OrderedDict[tuple[str, tuple[str, ...] | None], PlaybackProjection] = (
            OrderedDict()
        )
        self.sample_rate: int | None = None

    def supersede(self, *, sequence: int) -> bool:
        if self._closed or type(sequence) is not int or sequence <= self._sequence:
            return False
        self._sequence = sequence
        return True

    async def replace(
        self, *, sequence: int, carrier_id: str, note_ids: tuple[str, ...] | None = None
    ) -> int | None:
        snapshot = await require_accessible_draft(
            storage=self._storage, draft_id=self._draft_id, viewer_id=self._viewer_id
        )
        if self._closed or sequence != self._sequence:
            return None
        if snapshot.document.music_revision != self._music_revision:
            self._cache.clear()
            self._music_revision = snapshot.document.music_revision
        key = carrier_id, None if note_ids is None else tuple(sorted(set(note_ids)))
        projection = self._cache.get(key)
        if projection is None:
            try:
                projection = await asyncio.to_thread(
                    self._project,
                    document=snapshot.document,
                    carrier_id=carrier_id,
                    note_ids=key[1],
                )
            except (ValueError, PitchResolutionError) as error:
                raise PlaybackRejectedError(str(error)) from error
            if self._closed or sequence != self._sequence:
                return None
            self._cache[key] = projection
            if len(self._cache) > 32:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        await self._run(partial(self._replace, sequence, projection))
        return snapshot.version if sequence == self._sequence and not self._closed else None

    async def release(self, *, sequence: int) -> None:
        await self._run(partial(self._release, sequence))

    async def read(self, *, max_frames: int) -> tuple[int, AudioChunk] | None:
        return await self._run(partial(self._read, max_frames))

    async def _run(self, operation: Callable[[], _Result]) -> _Result:
        if self._closed:
            raise PlaybackUnavailableError("Live preview is closed.")
        return await asyncio.get_running_loop().run_in_executor(self._worker, operation)

    def _replace(self, sequence: int, projection: PlaybackProjection) -> None:
        if self._closed or sequence != self._sequence:
            return
        if self._native is None:
            self._native = self._renderer.open_session()
            self.sample_rate = self._native.sample_rate
        self._native.replace(projection=projection)
        self._rendered_sequence = sequence

    def _release(self, sequence: int) -> None:
        if not self._closed and sequence == self._sequence and self._native is not None:
            self._native.release()
            self._rendered_sequence = sequence

    def _read(self, max_frames: int) -> tuple[int, AudioChunk] | None:
        if self._closed or self._native is None:
            return None
        chunk = self._native.read(max_frames=max_frames)
        return (self._rendered_sequence, chunk) if chunk is not None else None

    async def close(self) -> None:
        if self._closing is None:
            self._closed = True
            self._closing = asyncio.create_task(self._finish_close())
        await asyncio.shield(self._closing)

    async def _finish_close(self) -> None:
        # Queued close follows any native operation whose awaiter was cancelled.
        def close_native() -> None:
            if self._native is not None:
                self._native.close()
                self._native = None

        try:
            await asyncio.get_running_loop().run_in_executor(self._worker, close_native)
        finally:
            self._worker.shutdown(wait=False)
            self._cache.clear()
            self._on_close(self)

    @staticmethod
    def _project(
        *, document: ScoreDocument, carrier_id: str, note_ids: tuple[str, ...] | None
    ) -> PlaybackProjection:
        return preview_projection(document=document, carrier_id=carrier_id, note_ids=note_ids)
