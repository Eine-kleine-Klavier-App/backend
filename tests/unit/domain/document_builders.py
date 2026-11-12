from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import MeasurePosition, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)


def score() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=3)


def anchor(document: ScoreDocument, at: Fraction) -> TemporalAnchor:
    measure = document.measures[int(at)]
    position = MeasurePosition(value=at - int(at))
    return next(
        (a for a in measure.anchors if a.position == position), None
    ) or TemporalAnchor.create(measure=measure, position=position)


def size(value: RhythmicValue = RhythmicValue.QUARTER, count: int = 1) -> RhythmicSize:
    return RhythmicSize(value=DottedRhythmicValue(value=value), count=count)


def note(
    document: ScoreDocument,
    at: Fraction,
    *,
    voice: int = 0,
    staff: int = 0,
    step: int = -2,
    value: RhythmicValue = RhythmicValue.QUARTER,
    parent: RhythmicContainerParent | None = None,
) -> Note:
    leaf = LeafRhythmicContainer.create(
        parent=document.voices[voice] if parent is None else parent,
        anchor=anchor(document, at),
        size=size(value),
    )
    return Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=document.staffs[staff],
        staff_step=step,
        accidental=Accidental.NATURAL,
    )
