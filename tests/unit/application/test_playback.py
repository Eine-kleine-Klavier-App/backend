from fractions import Fraction
from unittest.mock import Mock

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import (
    DraftNotFoundError,
    PlaybackCarrierNotFoundError,
    PlaybackRejectedError,
    PlaybackUnavailableError,
)
from piano_app.application.use_cases.score.playback import PlaybackService
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental


async def _draft(*, storage: InMemoryDraftHistory, document=None) -> str:  # type: ignore[no-untyped-def]
    draft = await storage.create(
        title="test",
        author_id="owner",
        ref_score_id=None,
        document=score() if document is None else document,
    )
    await storage.commit(draft=draft)
    return draft.draft_id


async def test_prepare_uses_accessible_snapshot_and_version() -> None:
    storage = InMemoryDraftHistory()
    document = score()
    first = note(document, Fraction(0))
    draft_id = await _draft(storage=storage, document=document)
    renderer = Mock()
    service = PlaybackService(storage=storage, renderer=renderer)

    prepared = await service.prepare(draft_id=draft_id, viewer_id="owner", start=Fraction(0))

    assert prepared.version == 1
    assert [note.source_id for note in prepared.projection.notes] == [first.id]
    renderer.stream.assert_not_called()
    assert prepared.renderer is renderer


async def test_other_owner_and_missing_draft_have_same_refusal() -> None:
    storage = InMemoryDraftHistory()
    draft_id = await _draft(storage=storage)
    service = PlaybackService(storage=storage, renderer=None)

    for checked_id, viewer in ((draft_id, "other"), ("missing", "owner")):
        with pytest.raises(DraftNotFoundError):
            await service.prepare(draft_id=checked_id, viewer_id=viewer, start=Fraction(0))

        with pytest.raises(DraftNotFoundError):
            await service.prepare_map(draft_id=checked_id, viewer_id=viewer)


async def test_unconfigured_renderer_and_invalid_coordinate() -> None:
    storage = InMemoryDraftHistory()
    draft_id = await _draft(storage=storage)

    with pytest.raises(PlaybackUnavailableError):
        await PlaybackService(storage=storage, renderer=None).prepare(
            draft_id=draft_id, viewer_id="owner", start=Fraction(0)
        )

    with pytest.raises(PlaybackRejectedError, match="outside"):
        await PlaybackService(storage=storage, renderer=Mock()).prepare(
            draft_id=draft_id, viewer_id="owner", start=Fraction(40)
        )


async def test_the_map_needs_no_renderer() -> None:
    storage = InMemoryDraftHistory()
    document = score()
    note(document, Fraction(0))
    draft_id = await _draft(storage=storage, document=document)

    projection, version = await PlaybackService(storage=storage, renderer=None).prepare_map(
        draft_id=draft_id, viewer_id="owner"
    )

    assert version == 1
    assert len(projection.notes) == 1


async def test_preview_loads_the_selected_carrier() -> None:
    storage = InMemoryDraftHistory()
    document = score()
    note(document, Fraction(0))
    added = note(document, Fraction(1, 4), step=0)
    draft_id = await _draft(storage=storage, document=document)
    service = PlaybackService(storage=storage, renderer=Mock())

    prepared = await service.prepare_preview(
        draft_id=draft_id, viewer_id="owner", carrier_id=added.note_carrier.id
    )

    assert [(n.source_id, n.pitch, n.end_ms) for n in prepared.projection.notes] == [
        (added.id, 64, 650.0)
    ]
    with pytest.raises(PlaybackCarrierNotFoundError):
        await service.prepare_preview(draft_id=draft_id, viewer_id="owner", carrier_id="foreign")


async def test_preview_subset_and_its_refusals() -> None:
    storage = InMemoryDraftHistory()
    document = score()
    first = note(document, Fraction(0))
    sharp = Note.create(
        note_carrier=first.note_carrier,
        staff=first.staff,
        staff_step=0,
        accidental=Accidental.SHARP,
    )
    draft_id = await _draft(storage=storage, document=document)
    service = PlaybackService(storage=storage, renderer=Mock())

    prepared = await service.prepare_preview(
        draft_id=draft_id,
        viewer_id="owner",
        carrier_id=first.note_carrier.id,
        note_ids=(sharp.id,),
    )

    assert [(n.source_id, n.pitch) for n in prepared.projection.notes] == [(sharp.id, 65)]
    with pytest.raises(PlaybackRejectedError):
        await service.prepare_preview(
            draft_id=draft_id,
            viewer_id="owner",
            carrier_id=first.note_carrier.id,
            note_ids=("missing",),
        )

    with pytest.raises(DraftNotFoundError):
        await service.prepare_preview(
            draft_id=draft_id,
            viewer_id="other",
            carrier_id=first.note_carrier.id,
            note_ids=(sharp.id,),
        )
