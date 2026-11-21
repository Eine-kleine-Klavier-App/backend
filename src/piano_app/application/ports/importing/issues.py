from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction


class IssueKind(StrEnum):
    SKIPPED = "skipped"
    """An element of the file the score has no place for; it is not in the draft."""

    CHANGED = "changed"
    """Something the importer had to alter to fit it in (a rounded accidental, an added rest)."""

    MISMATCH = "mismatch"
    """The draft differs from the file; found by comparing the two after the build."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportIssue:
    """One entry of the import report, tied to a measure of the file when it has one."""

    kind: IssueKind
    measure: str | None
    message: str
    onset: Fraction | None = None
    """Where in the measure, in quarter notes from its start (the start of anything that
    lasts); ``None`` when the entry has no place on a beat."""
