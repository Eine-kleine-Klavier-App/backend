import asyncio
from fractions import Fraction
from threading import Event

import pytest
from tests.unit.adapters.outbound.test_fluidsynth import FakeSession, preview_chord, renderer
from tests.unit.domain.document_builders import note, score

from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import DraftNotFoundError, PlaybackUnavailableError
from piano_app.application.use_cases.score.playback.preview_session import PreviewSessionService


async def fixture_session(native=None):
    storage = InMemoryDraftHistory()
    document = score()
    n = note(document, Fraction(0))
    draft = await storage.create(
        title="preview", author_id="owner", ref_score_id=None, document=document
    )
    native = native or FakeSession()
    service = PreviewSessionService(storage=storage, renderer=renderer(native, tail=100))
    session = await service.open(draft_id=draft.draft_id, viewer_id="owner")
    return storage, draft, n, service, session, native


async def test_projection_cache_tracks_music_revision_but_access_is_always_checked(monkeypatch):
    storage, draft, n, service, session, native = await fixture_session()
    original = session._project
    calls = []

    def project(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(session, "_project", project)
    try:
        for seq, ids in [(1, None), (2, None), (3, (n.id, n.id)), (4, (n.id,))]:
            assert session.supersede(sequence=seq)
            assert (
                await session.replace(sequence=seq, carrier_id=n.note_carrier.id, note_ids=ids) == 0
            )
            rendered = await session.read(max_frames=80)
            assert rendered is not None and rendered[0] == seq
        assert len(calls) == 2
        await storage.commit(draft=draft)
        session.supersede(sequence=5)
        assert await session.replace(sequence=5, carrier_id=n.note_carrier.id) == 1
        assert len(calls) == 2  # A storage-only revision preserves resolved music.
        snapshot = await storage.get(draft_id=draft.draft_id)
        snapshot.document.renew_music_revision()
        await storage.commit(draft=snapshot)
        session.supersede(sequence=6)
        assert await session.replace(sequence=6, carrier_id=n.note_carrier.id) == 2
        assert len(calls) == 3
        assert not session.supersede(sequence=4)
        assert not session.supersede(sequence=True)
    finally:
        await service.close()
    assert native.closed


async def test_old_projection_finishing_after_new_selection_cannot_attack(monkeypatch):
    _, _, n, service, session, native = await fixture_session()
    entered, finish = Event(), Event()
    original = session._project

    def slow(**kwargs):
        entered.set()
        assert finish.wait(2)
        return original(**kwargs)

    monkeypatch.setattr(session, "_project", slow)
    session.supersede(sequence=1)
    old = asyncio.create_task(session.replace(sequence=1, carrier_id=n.note_carrier.id))
    await asyncio.to_thread(entered.wait, 2)
    session.supersede(sequence=2)
    finish.set()
    assert await old is None
    assert native.events == []
    await session.release(sequence=2)
    assert await session.read(max_frames=80) is None
    await service.close()
    assert not native.closed  # No synth was allocated.


async def test_cancelled_native_read_finishes_before_resource_close():
    entered, finish = Event(), Event()

    class Slow(FakeSession):
        def read(self, *, frames):
            entered.set()
            assert finish.wait(2)
            assert not self.closed
            return super().read(frames=frames)

    _, _, n, service, session, native = await fixture_session(Slow())
    session.supersede(sequence=1)
    await session.replace(sequence=1, carrier_id=n.note_carrier.id)
    read = asyncio.create_task(session.read(max_frames=80))
    await asyncio.to_thread(entered.wait, 2)
    read.cancel()
    with pytest.raises(asyncio.CancelledError):
        await read
    close = asyncio.create_task(session.close())
    await asyncio.sleep(0)
    assert not native.closed
    finish.set()
    await close
    assert native.closed
    await service.close()


async def test_read_started_before_replacement_keeps_the_old_rendered_sequence():
    entered, finish = Event(), Event()

    class Slow(FakeSession):
        def read(self, *, frames):
            entered.set()
            assert finish.wait(2)
            return super().read(frames=frames)

    _, _, n, service, session, _ = await fixture_session(Slow())
    try:
        assert session.supersede(sequence=1)
        await session.replace(sequence=1, carrier_id=n.note_carrier.id)
        old = asyncio.create_task(session.read(max_frames=80))
        await asyncio.to_thread(entered.wait, 2)
        assert session.supersede(sequence=2)
        replacement = asyncio.create_task(session.replace(sequence=2, carrier_id=n.note_carrier.id))
        finish.set()
        rendered = await old
        assert rendered is not None and rendered[0] == 1
        assert await replacement == 0
        rendered = await session.read(max_frames=80)
        assert rendered is not None and rendered[0] == 2
    finally:
        finish.set()
        await service.close()


async def test_missing_foreign_and_unconfigured_sessions_do_not_allocate():
    storage, draft, _, service, session, _ = await fixture_session()
    for id, viewer in [(draft.draft_id, "other"), ("missing", "owner")]:
        with pytest.raises(DraftNotFoundError):
            await service.open(draft_id=id, viewer_id=viewer)
    unavailable = PreviewSessionService(storage=storage, renderer=None)
    with pytest.raises(PlaybackUnavailableError):
        await unavailable.open(draft_id=draft.draft_id, viewer_id="owner")
    await session.close()
    await service.close()


async def test_projection_cache_evicts_oldest_target_at_32_entries(monkeypatch):
    _, _, _, service, session, _ = await fixture_session()
    projection = preview_chord(pitches=[60], velocity=80)
    calls = []

    def project(**kwargs):
        calls.append(kwargs["carrier_id"])
        return projection

    monkeypatch.setattr(session, "_project", project)
    try:
        for sequence in range(1, 34):
            session.supersede(sequence=sequence)
            await session.replace(sequence=sequence, carrier_id=str(sequence))
        assert len(session._cache) == 32
        session.supersede(sequence=34)
        await session.replace(sequence=34, carrier_id="2")
        assert len(calls) == 33
        session.supersede(sequence=35)
        await session.replace(sequence=35, carrier_id="1")
        assert len(calls) == 34
    finally:
        await service.close()


async def test_session_limit_and_shutdown_release_every_connection():
    _, draft, _, service, session, _ = await fixture_session()
    for _ in range(31):
        await service.open(draft_id=draft.draft_id, viewer_id="owner")
    with pytest.raises(PlaybackUnavailableError):
        await service.open(draft_id=draft.draft_id, viewer_id="owner")
    await service.close()
    assert not service._sessions
    await session.close()
    await service.close()
