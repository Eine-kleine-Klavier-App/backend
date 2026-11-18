from typing import Any, Protocol

from piano_app.domain.score.document import ScoreDocument

# What a draft or a score is stored as: the document turned into plain data. Its shape is the
# codec's; everything else only moves it around and compares two of them (see record_patch).
type DocumentRecord = dict[str, Any]


class DocumentCodec(Protocol):
    """Turns a document into a record and back; a record always rebuilds the same document."""

    def serialize(self, document: ScoreDocument) -> DocumentRecord: ...

    def deserialize(self, data: DocumentRecord) -> ScoreDocument: ...
