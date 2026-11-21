from typing import Protocol

from .source import SourceScore


class ScoreFormatReader(Protocol):
    """Reads one file format into the source score. One adapter per format."""

    def detect(self, *, head: bytes, filename: str) -> bool:
        """Whether the file looks like this format, from its first bytes and its name."""
        ...

    def read(self, *, data: bytes) -> SourceScore:
        """Raises ``ImportRefusedError`` when the file cannot be imported at all."""
        ...
