import asyncio

import pytest
from tests.fixtures.drafts import in_memory_history

from piano_app.adapters.outbound.importers.musicxml.reader import MusicXmlReader
from piano_app.application.errors import (
    DraftNotFoundError,
    ImportBusyError,
    ImportFormatUnsupportedError,
    ImportJobNotFoundError,
)
from piano_app.application.ports.importing import SourceScore
from piano_app.application.use_cases.score.import_score.builder import ScoreBuilder
from piano_app.application.use_cases.score.import_score.compare import ScoreComparer
from piano_app.application.use_cases.score.import_score.jobs import (
    ImportJob,
    ImportJobs,
    ImportState,
)
from piano_app.application.use_cases.score.import_score.service import ImportService
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine

_SCORE: bytes = b"""<score-partwise><work><work-title>Etude</work-title></work>
<part-list/><part id="P1"><measure number="1"><attributes><divisions>1</divisions>
<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>
<clef number="1"><sign>G</sign><line>2</line></clef>
<clef number="2"><sign>F</sign><line>4</line></clef></attributes>
<direction><direction-type><words>dolce</words></direction-type><staff>1</staff></direction>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice>
<type>whole</type><staff>1</staff></note></measure></part></score-partwise>"""


class _BrokenBuilder(ScoreBuilder):
    def build(self, *, source: SourceScore):  # type: ignore[no-untyped-def]
        raise RuntimeError("an engine bug, not for the client")


def _service(
    *,
    storage: DraftHistoryService | None = None,
    jobs: ImportJobs | None = None,
    broken=False,  # type: ignore[no-untyped-def]
) -> tuple[ImportService, DraftHistoryService]:
    history = in_memory_history() if storage is None else storage
    builder_type = _BrokenBuilder if broken else ScoreBuilder
    service = ImportService(
        storage=history,
        readers=(MusicXmlReader(),),
        builder=builder_type(engine=build_engine(), compiler=build_compiler()),
        comparer=ScoreComparer(),
        jobs=ImportJobs() if jobs is None else jobs,
    )
    return service, history


async def _finished(service: ImportService, job: ImportJob, actor_id: str) -> ImportJob:
    for _ in range(500):
        current = service.state(job_id=job.job_id, actor_id=actor_id)
        if not current.is_active:
            return current
        await asyncio.sleep(0.01)
    raise AssertionError("the import did not end")


async def test_a_file_becomes_an_ordinary_draft_and_the_job_keeps_what_was_left_out() -> None:
    service, history = _service()

    job = await service.start(actor_id="owner", filename="etude.musicxml", data=_SCORE)
    assert job.state is ImportState.QUEUED
    done = await _finished(service, job, "owner")

    assert done.state is ImportState.DONE
    assert done.draft_id is not None
    draft = await history.get(draft_id=done.draft_id)
    assert draft is not None
    assert (draft.meta.title, draft.meta.author_id, draft.meta.ref_score_id) == (
        "Etude",
        "owner",
        None,
    )
    assert [(i.kind.value, i.measure_index, i.message) for i in done.comparison] == [
        ("skipped", 0, "<words> is not imported.")
    ]


async def test_a_file_that_cannot_be_read_fails_with_its_reason_and_makes_no_draft() -> None:
    service, history = _service()

    job = await service.start(actor_id="owner", filename="x.xml", data=b"<not xml")
    done = await _finished(service, job, "owner")

    assert done.state is ImportState.FAILED
    assert done.error == "The file is not readable MusicXML."
    assert done.draft_id is None
    assert await history.list_by_author(author_id="owner") == []


async def test_an_unexpected_failure_is_not_shown_to_the_client() -> None:
    service, _ = _service(broken=True)

    job = await service.start(actor_id="owner", filename="etude.musicxml", data=_SCORE)
    done = await _finished(service, job, "owner")

    assert done.state is ImportState.FAILED
    assert done.error == "The file could not be imported."


async def test_a_format_no_reader_knows_is_refused_at_once() -> None:
    service, _ = _service()

    with pytest.raises(ImportFormatUnsupportedError):
        await service.start(actor_id="owner", filename="score.pdf", data=b"%PDF-1.7")


async def test_a_job_is_seen_by_its_owner_only() -> None:
    service, _ = _service()
    job = await service.start(actor_id="owner", filename="etude.musicxml", data=_SCORE)

    for stranger, job_id in (("other", job.job_id), ("owner", "missing")):
        with pytest.raises(ImportJobNotFoundError):
            service.state(job_id=job_id, actor_id=stranger)

    await _finished(service, job, "owner")


async def test_an_owner_has_a_limited_number_of_imports_running() -> None:
    service, _ = _service(jobs=ImportJobs(active_per_owner=1))
    first = await service.start(actor_id="owner", filename="a.musicxml", data=_SCORE)

    with pytest.raises(ImportBusyError):
        await service.start(actor_id="owner", filename="b.musicxml", data=_SCORE)

    other = await service.start(actor_id="other", filename="c.musicxml", data=_SCORE)
    await _finished(service, first, "owner")
    await _finished(service, other, "other")
    again = await service.start(actor_id="owner", filename="d.musicxml", data=_SCORE)
    await _finished(service, again, "owner")


async def test_a_finished_job_is_forgotten_after_a_while() -> None:
    now = [0.0]
    service, _ = _service(jobs=ImportJobs(keep_seconds=60, clock=lambda: now[0]))
    job = await service.start(actor_id="owner", filename="a.musicxml", data=_SCORE)
    await _finished(service, job, "owner")

    now[0] = 61
    with pytest.raises(ImportJobNotFoundError):
        service.state(job_id=job.job_id, actor_id="owner")


_OTHER_PITCH: bytes = _SCORE.replace(b"<step>C</step>", b"<step>D</step>")


async def test_a_draft_is_compared_with_any_file_and_nothing_is_written() -> None:
    service, history = _service()
    imported = await _finished(
        service,
        await service.start(actor_id="owner", filename="etude.musicxml", data=_SCORE),
        "owner",
    )
    assert imported.draft_id is not None
    before = await history.get(draft_id=imported.draft_id)

    job = await service.compare(
        actor_id="owner", draft_id=imported.draft_id, filename="other.musicxml", data=_OTHER_PITCH
    )
    done = await _finished(service, job, "owner")

    assert done.state is ImportState.DONE
    assert done.draft_id == imported.draft_id
    assert [(i.kind.value, i.measure_index, i.message) for i in done.comparison] == [
        ("skipped", 0, "<words> is not imported."),
        ("mismatch", 0, "In the file but not in the draft: D5 at beat 1."),
        ("mismatch", 0, "In the draft but not in the file: C5 at beat 1."),
    ]
    after = await history.get(draft_id=imported.draft_id)
    assert before is not None and after is not None and after.version == before.version
    assert len(await history.list_by_author(author_id="owner")) == 1


async def test_only_the_owner_can_compare_a_draft_and_only_with_a_known_format() -> None:
    service, _ = _service()
    imported = await _finished(
        service,
        await service.start(actor_id="owner", filename="etude.musicxml", data=_SCORE),
        "owner",
    )
    assert imported.draft_id is not None

    with pytest.raises(DraftNotFoundError):
        await service.compare(
            actor_id="other", draft_id=imported.draft_id, filename="a.musicxml", data=_SCORE
        )

    with pytest.raises(ImportFormatUnsupportedError):
        await service.compare(
            actor_id="owner", draft_id=imported.draft_id, filename="a.pdf", data=b"%PDF"
        )
