from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    InsertNoteIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

# Scene builders shared by the mutation tests. Every bar is 4/4, so a position on the
# whole timeline reads as "bar index + position inside the bar". Notes already in a
# scene carry a staff step that names them; notes of an insert under test carry NEW_STEP.

NEW_STEP: int = 9


@dataclass(frozen=True, slots=True, kw_only=True)
class Score:
    document: ScoreDocument
    voice: Voice
    staff: Staff
    measures: list[Measure]


def build_score(*, bars: int) -> Score:
    measures: list[Measure] = [Measure.create() for _ in range(bars)]
    voice: Voice = Voice()
    staff: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[staff], measures=measures
    )

    return Score(document=document, voice=voice, staff=staff, measures=measures)


def value(rhythmic_value: RhythmicValue, dots: int = 0) -> DottedRhythmicValue:
    return DottedRhythmicValue(value=rhythmic_value, dots_count=dots)


def size(rhythmic_value: RhythmicValue, count: int = 1) -> RhythmicSize:
    return RhythmicSize(value=value(rhythmic_value), count=count)


def anchor_at(*, score: Score, at: Fraction) -> TemporalAnchor:
    """The anchor at a timeline position, reused when it already exists."""
    measure: Measure = score.measures[int(at)]
    position: MeasurePosition = MeasurePosition.of_fraction(fraction=at - int(at))

    existing: TemporalAnchor | None = next(
        (anchor for anchor in measure.anchors if anchor.position == position),
        None,
    )
    return existing or TemporalAnchor.create(measure=measure, position=position)


def note(
    *,
    score: Score,
    parent: RhythmicContainerParent,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    step: int,
) -> LeafRhythmicContainer:
    """A leaf holding one note already in the scene."""
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=parent,
        anchor=anchor_at(score=score, at=at),
        size=size(rhythmic_value),
    )
    Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=score.staff,
        staff_step=step,
        accidental=Accidental.NATURAL,
    )

    return leaf


def group(
    *,
    score: Score,
    parent: RhythmicContainerParent,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
) -> GroupRhythmicContainer:
    """A group starting at its own anchor, attached at once and still empty."""
    return GroupRhythmicContainer.create(
        parent=parent,
        anchor=anchor_at(score=score, at=at),
        written_size=written,
        occupied_size=occupied,
    )


def eighth_triplet(
    *,
    score: Score,
    parent: RhythmicContainerParent,
    at: Fraction,
) -> GroupRhythmicContainer:
    """Three eighths in the time of a quarter starting at ``at``, staff steps 1, 2, 3."""
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=parent,
        at=at,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    for index in range(3):
        note(
            score=score,
            parent=triplet,
            at=at + Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )

    return triplet


def quarters(*, score: Score, bar: int, beats: Sequence[int] = (0, 1, 2, 3)) -> None:
    for beat in beats:
        note(
            score=score,
            parent=score.voice,
            at=bar + Fraction(beat, 4),
            rhythmic_value=RhythmicValue.QUARTER,
            step=0,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Slot:
    """A leaf reduced to what the tests compare: where it starts, its written value, its
    depth (0 = in the voice), and what it holds — ``rest`` or the staff steps of its
    notes."""

    measure_index: int
    position: Fraction
    written: Fraction
    depth: int
    content: str


def _depth(*, container: RhythmicContainer) -> int:
    depth: int = 0
    parent: RhythmicContainerParent = container.parent
    while isinstance(parent, GroupRhythmicContainer):
        depth += 1
        parent = parent.parent

    return depth


def layout(*, score: Score) -> list[Slot]:
    slots: list[Slot] = []
    leaves: list[LeafRhythmicContainer] = []
    pending: list[RhythmicContainer] = list(reversed(score.voice.children))
    while pending:
        container: RhythmicContainer = pending.pop()
        if isinstance(container, GroupRhythmicContainer):
            pending.extend(reversed(container.children))
        else:
            assert isinstance(container, LeafRhythmicContainer)
            leaves.append(container)

    for leaf in leaves:
        carrier = leaf.carrier
        content: str = (
            "rest"
            if isinstance(carrier, RestCarrier)
            else ",".join(str(item.staff_step) for item in carrier.notes)
            if isinstance(carrier, NoteCarrier)
            else "empty"
        )
        slots.append(
            Slot(
                measure_index=score.measures.index(leaf.anchor.measure),
                position=leaf.anchor.position.value,
                written=leaf.written_size.fraction,
                depth=_depth(container=leaf),
                content=content,
            )
        )

    return slots


def slot(
    bar: int,
    position: Fraction,
    written: Fraction,
    content: str,
    *,
    depth: int = 0,
) -> Slot:
    return Slot(
        measure_index=bar,
        position=position,
        written=written,
        depth=depth,
        content=content,
    )


def tie_pairs(*, score: Score) -> list[tuple[int, int]]:
    """Every tie as (staff step of its start note, staff step of its end note)."""
    pairs: set[tuple[int, int]] = set()
    for item in score.staff.musical_items:
        if isinstance(item, Note):
            for relation in item.relations:
                if isinstance(relation, Tie):
                    pairs.add((relation.start.staff_step, relation.end.staff_step))

    return sorted(pairs)


def orphan_anchors(*, score: Score) -> list[TemporalAnchor]:
    return [anchor for measure in score.measures for anchor in measure.anchors if anchor.is_orphan]


def insert_note(
    *,
    score: Score,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    dots: int = 0,
    step: int = NEW_STEP,
) -> MutationLog:
    intent: InsertNoteIntent = InsertNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_value=value(rhythmic_value, dots),
        staff_step=step,
        accidental=Accidental.NATURAL,
    )

    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


def delete_entities(*, score: Score, entity_ids: Sequence[str]) -> MutationLog:
    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(
            document=score.document,
            intent=DeleteBatchIntent(entity_ids=tuple(entity_ids)),
        ),
    )
