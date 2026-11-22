import asyncio
import logging
from collections.abc import Coroutine, Sequence

from piano_app.application.errors import DraftNotFoundError, ImportFormatUnsupportedError
from piano_app.application.ports.importing import (
    ImportRefusedError,
    ScoreFormatReader,
    SourceScore,
)
from piano_app.application.ports.score import DraftStore, VersionedDraftDocument
from piano_app.application.use_cases.score.shared.draft_access import require_accessible_draft

from .builder import BuiltScore, ScoreBuilder
from .compare import ScoreComparer
from .jobs import ImportJob, ImportJobs, ImportState

_LOG: logging.Logger = logging.getLogger(__name__)

_UNTITLED: str = "Untitled"
_HEAD_BYTES: int = 1024
_MAX_TITLE: int = 200


class ImportService:
    """Turns an uploaded file into an ordinary draft, in the background.

    ``start`` answers at once with the job; the file is read and built in worker threads, and the
    draft is made when the build ends. What the import adds to the draft (what was left out or
    changed) goes to the job, not to the draft."""

    def __init__(
        self,
        *,
        storage: DraftStore,
        readers: Sequence[ScoreFormatReader],
        builder: ScoreBuilder,
        comparer: ScoreComparer,
        jobs: ImportJobs,
    ) -> None:
        self._storage: DraftStore = storage
        self._readers: Sequence[ScoreFormatReader] = readers
        self._builder: ScoreBuilder = builder
        self._comparer: ScoreComparer = comparer
        self._jobs: ImportJobs = jobs
        self._running: set[asyncio.Task[None]] = set()

    async def start(self, *, actor_id: str, filename: str, data: bytes) -> ImportJob:
        """Imports the file as a new draft; the job ends with the draft and its comparison with
        the file."""
        reader: ScoreFormatReader = self._reader_for(filename=filename, data=data)
        job: ImportJob = self._jobs.create(owner_id=actor_id)
        self._spawn(self._import(job=job, reader=reader, data=data))
        return job

    async def compare(
        self, *, actor_id: str, draft_id: str, filename: str, data: bytes
    ) -> ImportJob:
        """Compares a draft of the caller's with a file; nothing is written."""
        await require_accessible_draft(storage=self._storage, draft_id=draft_id, viewer_id=actor_id)
        reader: ScoreFormatReader = self._reader_for(filename=filename, data=data)
        job: ImportJob = self._jobs.create(owner_id=actor_id)
        job.draft_id = draft_id
        self._spawn(self._compare(job=job, reader=reader, data=data, draft_id=draft_id))
        return job

    def state(self, *, job_id: str, actor_id: str) -> ImportJob:
        return self._jobs.get(job_id=job_id, owner_id=actor_id)

    def _reader_for(self, *, filename: str, data: bytes) -> ScoreFormatReader:
        reader: ScoreFormatReader | None = next(
            (r for r in self._readers if r.detect(head=data[:_HEAD_BYTES], filename=filename)),
            None,
        )
        if reader is None:
            raise ImportFormatUnsupportedError

        return reader

    def _spawn(self, work: Coroutine[None, None, None]) -> None:
        task: asyncio.Task[None] = asyncio.create_task(work)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _import(self, *, job: ImportJob, reader: ScoreFormatReader, data: bytes) -> None:
        try:
            job.state = ImportState.READING
            source: SourceScore = await asyncio.to_thread(reader.read, data=data)
            job.state = ImportState.BUILDING
            built: BuiltScore = await asyncio.to_thread(self._builder.build, source=source)
            created: VersionedDraftDocument = await self._storage.create(
                title=(source.title or _UNTITLED)[:_MAX_TITLE],
                author_id=job.owner_id,
                ref_score_id=None,
                document=built.document,
            )
            job.draft_id = created.draft_id
            job.state = ImportState.COMPARING
            job.comparison = await asyncio.to_thread(
                self._comparer.compare, document=built.document, source=source
            )
            job.state = ImportState.DONE
        except ImportRefusedError as refused:
            job.error = refused.reason
            job.state = ImportState.FAILED
        except Exception:
            _LOG.exception("An import failed unexpectedly.")
            job.error = "The file could not be imported."
            job.state = ImportState.FAILED
        finally:
            self._jobs.finish(job=job)

    async def _compare(
        self, *, job: ImportJob, reader: ScoreFormatReader, data: bytes, draft_id: str
    ) -> None:
        try:
            job.state = ImportState.READING
            source: SourceScore = await asyncio.to_thread(reader.read, data=data)
            job.state = ImportState.COMPARING
            draft: VersionedDraftDocument = await require_accessible_draft(
                storage=self._storage, draft_id=draft_id, viewer_id=job.owner_id
            )
            job.comparison = await asyncio.to_thread(
                self._comparer.compare, document=draft.document, source=source
            )
            job.state = ImportState.DONE
        except ImportRefusedError as refused:
            job.error = refused.reason
            job.state = ImportState.FAILED
        except DraftNotFoundError:
            job.error = "The draft is gone."
            job.state = ImportState.FAILED
        except Exception:
            _LOG.exception("A comparison failed unexpectedly.")
            job.error = "The file could not be compared."
            job.state = ImportState.FAILED
        finally:
            self._jobs.finish(job=job)
