"""Draft application orchestration for playback of an accessible editing snapshot."""

from asyncio import to_thread
from dataclasses import dataclass
from fractions import Fraction

from piano_app.application.errors import (
    PlaybackCarrierNotFoundError,
    PlaybackRejectedError,
    PlaybackUnavailableError,
)
from piano_app.application.ports.playback import PlaybackRenderer
from piano_app.application.ports.score import DraftStore
from piano_app.application.use_cases.score.shared.draft_access import require_accessible_draft
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.playback import (
    PlaybackProjection,
    build_projection,
    preview_chord,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PreparedPlayback:
    projection: PlaybackProjection
    version: int
    renderer: PlaybackRenderer


class PlaybackService:
    def __init__(self, *, storage: DraftStore, renderer: PlaybackRenderer | None) -> None:
        self._storage = storage
        self._renderer = renderer

    async def prepare_map(self, *, draft_id: str, viewer_id: str) -> tuple[PlaybackProjection, int]:
        snapshot = await require_accessible_draft(
            storage=self._storage, draft_id=draft_id, viewer_id=viewer_id
        )
        try:
            projection = await to_thread(build_projection, document=snapshot.document)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return projection, snapshot.version

    async def prepare(
        self,
        *,
        draft_id: str,
        viewer_id: str,
        start: Fraction,
    ) -> PreparedPlayback:
        snapshot = await require_accessible_draft(
            storage=self._storage,
            draft_id=draft_id,
            viewer_id=viewer_id,
        )
        renderer = self._require_renderer()
        try:
            projection = await to_thread(build_projection, document=snapshot.document, start=start)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return PreparedPlayback(projection=projection, version=snapshot.version, renderer=renderer)

    async def prepare_preview_map(
        self, *, draft_id: str, viewer_id: str
    ) -> tuple[dict[str, PlaybackProjection], int]:
        snapshot = await require_accessible_draft(
            storage=self._storage, draft_id=draft_id, viewer_id=viewer_id
        )
        try:
            projections = await to_thread(preview_map, document=snapshot.document)
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return projections, snapshot.version

    async def prepare_preview(
        self,
        *,
        draft_id: str,
        viewer_id: str,
        carrier_id: str,
        note_ids: tuple[str, ...] | None = None,
    ) -> PreparedPlayback:
        snapshot = await require_accessible_draft(
            storage=self._storage,
            draft_id=draft_id,
            viewer_id=viewer_id,
        )
        renderer = self._require_renderer()
        try:
            projection = await to_thread(
                preview_projection,
                document=snapshot.document,
                carrier_id=carrier_id,
                note_ids=note_ids,
            )
        except (ValueError, PitchResolutionError) as error:
            raise PlaybackRejectedError(str(error)) from error
        return PreparedPlayback(projection=projection, version=snapshot.version, renderer=renderer)

    def _require_renderer(self) -> PlaybackRenderer:
        if self._renderer is None:
            raise PlaybackUnavailableError("Server playback is not configured.")
        return self._renderer


def preview_map(*, document: ScoreDocument) -> dict[str, PlaybackProjection]:
    projections: dict[str, PlaybackProjection] = {}
    for voice in document.voices:
        for leaf in iter_leaves(voice):
            carriers: list[Carrier | None] = [leaf.carrier]
            for group in (leaf.grace_before, leaf.grace_after):
                if group is not None:
                    carriers.extend(item.carrier for item in group.grace_items)
            for carrier in carriers:
                if isinstance(carrier, NoteCarrier):
                    projections[carrier.id] = preview_chord(document=document, carrier=carrier)
    return projections


def preview_projection(
    *, document: ScoreDocument, carrier_id: str, note_ids: tuple[str, ...] | None = None
) -> PlaybackProjection:
    """The projection of one carrier (a grace carrier too) or some of its notes, for an audition."""
    for voice in document.voices:
        for leaf in iter_leaves(voice):
            carriers: list[Carrier | None] = [leaf.carrier]
            for group in (leaf.grace_before, leaf.grace_after):
                if group is not None:
                    carriers.extend(item.carrier for item in group.grace_items)

            for carrier in carriers:
                if isinstance(carrier, NoteCarrier) and carrier.id == carrier_id:
                    return preview_chord(document=document, carrier=carrier, note_ids=note_ids)
    raise PlaybackCarrierNotFoundError("Note carrier not found in this draft.")
