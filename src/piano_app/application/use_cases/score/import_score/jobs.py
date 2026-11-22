from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from uuid import uuid4

from piano_app.application.errors import ImportBusyError, ImportJobNotFoundError

from .compare import ComparisonIssue

DEFAULT_KEEP_SECONDS: float = 3600
DEFAULT_ACTIVE_PER_OWNER: int = 2
DEFAULT_ACTIVE_TOTAL: int = 4


class ImportState(StrEnum):
    QUEUED = "queued"
    READING = "reading"
    BUILDING = "building"
    COMPARING = "comparing"
    DONE = "done"
    FAILED = "failed"


@dataclass(slots=True, kw_only=True)
class ImportJob:
    """One import, or one comparison of a draft with a file, as the client sees it: where it is,
    and how it ended.

    The draft a finished import made is an ordinary draft. What the comparison found lives here
    for a while and is not stored anywhere else; a new comparison finds it again."""

    job_id: str
    owner_id: str
    state: ImportState = ImportState.QUEUED
    draft_id: str | None = None
    comparison: tuple[ComparisonIssue, ...] = ()
    error: str | None = None
    finished_at: float | None = field(default=None, repr=False)

    @property
    def is_active(self) -> bool:
        return self.state not in (ImportState.DONE, ImportState.FAILED)


class ImportJobs:
    """The imports of this process, kept for a while after they end so the client can ask.

    Used from the event loop only, so it needs no lock. Imports in flight are lost on a restart;
    the draft of one that had ended stays."""

    def __init__(
        self,
        *,
        keep_seconds: float = DEFAULT_KEEP_SECONDS,
        active_per_owner: int = DEFAULT_ACTIVE_PER_OWNER,
        active_total: int = DEFAULT_ACTIVE_TOTAL,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._keep_seconds: float = keep_seconds
        self._active_per_owner: int = active_per_owner
        self._active_total: int = active_total
        self._clock: Callable[[], float] = clock
        self._jobs: dict[str, ImportJob] = {}

    def create(self, *, owner_id: str) -> ImportJob:
        """Raises ``ImportBusyError`` when the owner or the process has its share running."""
        self._forget_old()
        active: list[ImportJob] = [job for job in self._jobs.values() if job.is_active]
        if len(active) >= self._active_total or (
            sum(1 for job in active if job.owner_id == owner_id) >= self._active_per_owner
        ):
            raise ImportBusyError

        job: ImportJob = ImportJob(job_id=uuid4().hex, owner_id=owner_id)
        self._jobs[job.job_id] = job
        return job

    def get(self, *, job_id: str, owner_id: str) -> ImportJob:
        """Raises ``ImportJobNotFoundError`` for an unknown job and for another owner's."""
        self._forget_old()
        job: ImportJob | None = self._jobs.get(job_id)
        if job is None or job.owner_id != owner_id:
            raise ImportJobNotFoundError

        return job

    def finish(self, *, job: ImportJob) -> None:
        job.finished_at = self._clock()

    def _forget_old(self) -> None:
        now: float = self._clock()
        for job_id in [
            job.job_id
            for job in self._jobs.values()
            if job.finished_at is not None and now - job.finished_at > self._keep_seconds
        ]:
            del self._jobs[job_id]
