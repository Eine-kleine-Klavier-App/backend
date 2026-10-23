from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure


def neighbour_signature(*, document: ScoreDocument, before: Measure | None) -> RhythmicSize:
    """The time signature a new measure takes (measure-operations): its left neighbour's, or
    its right neighbour's when it goes before the first measure; the last measure's when it
    goes after the last."""
    if not document.measures:
        raise ValueError("A document always holds a measure to take a signature from.")

    if before is None:
        return document.measures[-1].time_signature

    if before not in document.measures:
        raise ValueError("A measure is inserted before a measure of its document.")

    neighbour: Measure = before.prev_measure if before.prev_measure is not None else before

    return neighbour.time_signature
