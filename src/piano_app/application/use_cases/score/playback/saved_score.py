from asyncio import to_thread
from fractions import Fraction

from piano_app.application.errors import (
    PlaybackRejectedError,
    PlaybackUnavailableError,
    ScoreNotFoundError,
)
from piano_app.application.ports import ScoreUoWFactory
from piano_app.application.ports.playback import PlaybackRenderer
from piano_app.application.use_cases.score.playback.service import PreparedPlayback, preview_map
from piano_app.application.use_cases.score.shared import require_readable_score_meta
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.playback import PlaybackProjection, build_projection


class SavedScorePlaybackService:
    """Plays a readable saved version without creating or touching an editing draft."""

    def __init__(
        self, *, score_uow_factory: ScoreUoWFactory, renderer: PlaybackRenderer | None
    ) -> None:
        self._score_uow_factory = score_uow_factory
        self._renderer = renderer

    async def prepare_map(
        self, *, score_id: str, viewer_id: str | None
    ) -> tuple[PlaybackProjection, int]:
        async with self._score_uow_factory() as uow:
            meta = await require_readable_score_meta(
                score_repository=uow.score_repository, score_id=score_id, viewer_id=viewer_id
            )
            if not meta.is_public and viewer_id is None:
                raise ScoreNotFoundError(score_id=score_id)
            snapshot = await uow.score_repository.get_versioned(score_id=score_id)
            if snapshot is None:
                raise ScoreNotFoundError(score_id=score_id)
            score, version = snapshot
        try:
            projection = await to_thread(build_projection, document=score.document)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return projection, version

    async def prepare_preview_map(
        self, *, score_id: str, viewer_id: str | None
    ) -> tuple[dict[str, PlaybackProjection], int]:
        async with self._score_uow_factory() as uow:
            meta = await require_readable_score_meta(
                score_repository=uow.score_repository, score_id=score_id, viewer_id=viewer_id
            )
            if not meta.is_public and viewer_id is None:
                raise ScoreNotFoundError(score_id=score_id)
            snapshot = await uow.score_repository.get_versioned(score_id=score_id)
            if snapshot is None:
                raise ScoreNotFoundError(score_id=score_id)
            score, version = snapshot
        try:
            projections = await to_thread(preview_map, document=score.document)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return projections, version

    async def prepare(
        self, *, score_id: str, viewer_id: str | None, start: Fraction
    ) -> PreparedPlayback:
        async with self._score_uow_factory() as uow:
            meta = await require_readable_score_meta(
                score_repository=uow.score_repository, score_id=score_id, viewer_id=viewer_id
            )
            if not meta.is_public and viewer_id is None:
                raise ScoreNotFoundError(score_id=score_id)
            snapshot = await uow.score_repository.get_versioned(score_id=score_id)
            if snapshot is None:
                raise ScoreNotFoundError(score_id=score_id)
            score, version = snapshot
        renderer = self._renderer
        if renderer is None:
            raise PlaybackUnavailableError("Server playback is not configured.")
        try:
            projection = await to_thread(build_projection, document=score.document, start=start)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return PreparedPlayback(projection=projection, version=version, renderer=renderer)
