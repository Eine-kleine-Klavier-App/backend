from pydantic import BaseModel, Field

from piano_app.application.use_cases.score.import_score.compare import ComparisonIssue
from piano_app.application.use_cases.score.import_score.jobs import ImportJob


class OnsetResponse(BaseModel):
    numerator: int
    denominator: int


class ComparisonIssueResponse(BaseModel):
    kind: str = Field(description="skipped, changed or mismatch")
    measure_index: int | None = Field(
        description="The measure of the draft the entry is about, counted from 0"
    )
    onset: OnsetResponse | None = Field(
        description="Where in the measure, in quarter notes from its start (the start of anything "
        "that lasts); null when the entry has no place on a beat"
    )
    message: str

    @classmethod
    def from_issue(cls, issue: ComparisonIssue) -> ComparisonIssueResponse:
        return cls(
            kind=issue.kind.value,
            measure_index=issue.measure_index,
            onset=None
            if issue.onset is None
            else OnsetResponse(
                numerator=issue.onset.numerator, denominator=issue.onset.denominator
            ),
            message=issue.message,
        )


class ImportJobResponse(BaseModel):
    job_id: str
    state: str = Field(description="queued, reading, building, comparing, done or failed")
    draft_id: str | None = Field(
        description="The draft made by an import, or the draft a comparison is about"
    )
    comparison: list[ComparisonIssueResponse] = Field(
        description="How the draft differs from the file; set when done"
    )
    error: str | None = Field(description="Why the file was refused; set when failed")

    @classmethod
    def from_job(cls, job: ImportJob) -> ImportJobResponse:
        return cls(
            job_id=job.job_id,
            state=job.state.value,
            draft_id=job.draft_id,
            comparison=[ComparisonIssueResponse.from_issue(issue) for issue in job.comparison],
            error=job.error,
        )
