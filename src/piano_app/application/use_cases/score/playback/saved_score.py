from asyncio import to_thread

from piano_app.application.errors import (
    PlaybackRejectedError,
    ScoreNotFoundError,
)
from piano_app.application.ports import ScoreUoWFactory
from piano_app.application.use_cases.score.shared import require_readable_score_meta
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.playback import (
    PlaybackProjection,
    build_projection,
    preview_chord,
)


class SavedScorePlaybackService:
    """Plays a readable saved version without creating or touching an editing draft."""

    def __init__(self, *, score_uow_factory: ScoreUoWFactory) -> None:
        self._score_uow_factory = score_uow_factory

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

    async def prepare_preview_carrier(
        self, *, score_id: str, viewer_id: str | None, carrier_id: str
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
            projection = await to_thread(
                preview_carrier, document=score.document, carrier_id=carrier_id
            )
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return projection, version


def preview_carrier(*, document: ScoreDocument, carrier_id: str) -> PlaybackProjection:
    """The chord of one note carrier, struck as the preview plays it."""
    for voice in document.voices:
        for leaf in iter_leaves(voice):
            carriers: list[Carrier | None] = [leaf.carrier]
            for group in (leaf.grace_before, leaf.grace_after):
                if group is not None:
                    carriers.extend(item.carrier for item in group.grace_items)
            for carrier in carriers:
                if isinstance(carrier, NoteCarrier) and carrier.id == carrier_id:
                    return preview_chord(document=document, carrier=carrier)

    raise ValueError(f"The score has no note carrier {carrier_id!r} to preview.")
