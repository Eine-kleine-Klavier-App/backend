from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import partial
from typing import cast

import pytest

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
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
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import (
    Frame,
    FrameMismatchError,
    OutsideFrameError,
    Point,
    Span,
    Transform,
    UnreachableFrameError,
    interior,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation import (
    MutationEditor,
    build_compiler,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithNoteIntent,
    DeleteBatchIntent,
    EditIntent,
    InsertNoteIntent,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    intents as compiler_intents,
)
from piano_app.domain.score.document.services.mutation.compiler.intents.create import (
    DEFAULT_BEAM_SHARE,
)
from piano_app.domain.score.document.services.mutation.engine import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.factory import (
    build_analyzer_registry,
    build_handler_registry,
)
from piano_app.domain.score.document.services.mutation.engine.factory import (
    build_engine as production_build_engine,
)
from piano_app.domain.score.document.services.mutation.engine.guards import RelationGuard
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

# Scene builders shared by the mutation tests. Every measure is 4/4, so a position on the
# whole timeline reads as "measure index + position inside the measure". Notes already in a
# scene carry a staff step that names them; notes of an insert under test carry NEW_STEP.

NEW_STEP: int = 9


@dataclass(frozen=True, slots=True, kw_only=True)
class Score:
    document: ScoreDocument
    voice: Voice
    staff: Staff
    measures: list[Measure]
    # the contexts every score starts with, which a layout of the test's own contexts leaves out
    start_context_ids: frozenset[str] = frozenset()


def start_context_ids(document: ScoreDocument) -> frozenset[str]:
    """The ids of what the document holds at its very start."""
    return frozenset(
        context.id
        for anchor in document.measures[0].anchors
        for context in anchor.starting_contexts
    )


def build_score(*, measure_count: int, start_contexts: bool = True) -> Score:
    return build_score_with(
        time_signatures=[size(RhythmicValue.QUARTER, count=4)] * measure_count,
        start_contexts=start_contexts,
    )


def build_score_with(
    *, time_signatures: Sequence[RhythmicSize], start_contexts: bool = True
) -> Score:
    """Build one voice on one staff over measures of the given signatures.

    A position in such a scene still reads "measure index + position inside the measure". The
    contexts every score starts with are there unless ``start_contexts`` is off, for a test
    of the engine's own mechanism that wants nothing at the start.
    """
    measures: list[Measure] = [
        Measure.create(time_signature=time_signature) for time_signature in time_signatures
    ]
    voice: Voice = Voice()
    staff: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[staff], measures=measures
    )
    if start_contexts:
        document.place_start_contexts()

    return Score(
        document=document,
        voice=voice,
        staff=staff,
        measures=measures,
        start_context_ids=start_context_ids(document) if start_contexts else frozenset(),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Piano:
    """One voice over two staffs."""

    document: ScoreDocument
    voice: Voice
    upper: Staff
    lower: Staff
    measures: list[Measure]
    start_context_ids: frozenset[str] = frozenset()


def build_piano(*, measure_count: int = 1) -> Piano:
    measures: list[Measure] = [Measure.create() for _ in range(measure_count)]
    voice: Voice = Voice()
    upper: Staff = Staff()
    lower: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice],
        staffs=[upper, lower],
        measures=measures,
    )
    document.place_start_contexts()

    return Piano(
        document=document,
        voice=voice,
        upper=upper,
        lower=lower,
        measures=measures,
        start_context_ids=start_context_ids(document),
    )


def build_two_voices(*, measure_count: int) -> tuple[Score, Score]:
    """Two voices on one staff, each seen as a score of its own over the same document."""
    measures: list[Measure] = [Measure.create() for _ in range(measure_count)]
    first: Voice = Voice()
    second: Voice = Voice()
    staff: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[first, second],
        staffs=[staff],
        measures=measures,
    )
    document.place_start_contexts()

    ids: frozenset[str] = start_context_ids(document)
    return (
        Score(
            document=document, voice=first, staff=staff, measures=measures, start_context_ids=ids
        ),
        Score(
            document=document, voice=second, staff=staff, measures=measures, start_context_ids=ids
        ),
    )


def own_contexts(scene: Score | Piano, contexts: Sequence[Context]) -> list[Context]:
    """The contexts a test made itself: those of a staff or a voice without the ones every
    score starts with."""
    return [context for context in contexts if context.id not in scene.start_context_ids]


def anchor_positions(measure: Measure) -> list[Fraction]:
    """Where the measure's anchors lie: the start of a measure of the first one is always there,
    holding the contexts every score starts with."""
    return [anchor.position.value for anchor in measure.anchors]


def with_start_contexts(document: ScoreDocument) -> ScoreDocument:
    """The document with the contexts every score holds at its start, for a test that
    assembles one from its parts."""
    document.place_start_contexts()
    return document


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
    dots: int = 0,
) -> LeafRhythmicContainer:
    """A leaf holding one note already in the scene."""
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=parent,
        anchor=anchor_at(score=score, at=at),
        size=RhythmicSize(value=value(rhythmic_value, dots), count=1),
    )
    Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=score.staff,
        staff_step=step,
        accidental=Accidental.NATURAL,
    )

    return leaf


def rest(
    *,
    score: Score,
    parent: RhythmicContainerParent,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    staff: Staff | None = None,
) -> LeafRhythmicContainer:
    """A leaf holding one rest already in the scene, on the score's staff unless given."""
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=parent,
        anchor=anchor_at(score=score, at=at),
        size=size(rhythmic_value),
    )
    Rest.create(
        rest_carrier=RestCarrier.create(owner=leaf),
        staff=staff if staff is not None else score.staff,
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


def quarters(*, score: Score, measure: int, beats: Sequence[int] = (0, 1, 2, 3)) -> None:
    for beat in beats:
        note(
            score=score,
            parent=score.voice,
            at=measure + Fraction(beat, 4),
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
            else ",".join(str(step) for step in sorted(item.staff_step for item in carrier.notes))
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
    measure: int,
    position: Fraction,
    written: Fraction,
    content: str,
    *,
    depth: int = 0,
) -> Slot:
    return Slot(
        measure_index=measure,
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


def find_carriers(*, containers: Sequence[RhythmicContainer]) -> list[Carrier]:
    """The carriers of every leaf among ``containers`` or inside them, in their order."""
    carriers: list[Carrier] = []
    for container in containers:
        leaves: list[LeafRhythmicContainer]
        if isinstance(container, LeafRhythmicContainer):
            leaves = [container]
        elif isinstance(container, GroupRhythmicContainer):
            leaves = iter_leaves(container)
        else:
            raise TypeError(f"Unsupported rhythmic container type: {type(container).__name__}.")

        for leaf in leaves:
            if leaf.carrier is not None:
                carriers.append(leaf.carrier)

    return carriers


def tell_geometry(
    *,
    geometry: ScoreGeometry,
    entity: Measure | TemporalAnchor | RhythmicContainer,
) -> None:
    """Deliver a changed entity to the geometry the way the analyzers do, by its kind."""
    if isinstance(entity, Measure):
        geometry.invalidate_measures()
    elif isinstance(entity, TemporalAnchor):
        geometry.invalidate_anchor(anchor=entity)
    elif isinstance(entity, LeafRhythmicContainer):
        geometry.invalidate_leaf(leaf=entity)
    elif isinstance(entity, GroupRhythmicContainer):
        geometry.invalidate_group(group=entity)
    else:
        raise TypeError(f"Cannot deliver {type(entity).__name__} to the geometry.")


def check_geometry_after_action(geometry: ScoreGeometry, document: ScoreDocument) -> None:
    """An engine's ``geometry_check``: after every action the live geometry answers as a fresh
    build, even where the document is caught mid-edit."""
    differences: list[str] = transient_geometry_differences(geometry=geometry, document=document)
    assert differences == [], differences


def check_geometry_at_checkpoint(geometry: ScoreGeometry, document: ScoreDocument) -> None:
    """An engine's ``checkpoint_geometry_check``: at each check point of a pass the live geometry
    answers as a fresh build and as the model read directly."""
    differences: list[str] = geometry_differences(geometry=geometry, document=document)
    assert differences == [], differences


_PITCH_PROBE_STEP: Fraction = Fraction(1, 8)
# probes past the end of the timeline: a shortened one must stop answering there
_PITCH_PROBES_PAST_THE_END: int = 8

type _PitchOutcome = int | str


def _pitch_outcome(
    *,
    index: ScorePitch,
    staff: Staff,
    point: Point,
    staff_step: int,
    accidental: Accidental,
) -> _PitchOutcome:
    try:
        return index.resolve(
            staff=staff, point=point, staff_step=staff_step, accidental=accidental
        ).midi_note
    except PitchResolutionError:
        return "no rule"


def check_pitch_at_checkpoint(
    pitch: ScorePitch, geometry: ScoreGeometry, document: ScoreDocument
) -> None:
    """An engine's ``checkpoint_pitch_check``: at each check point of a pass the transaction's
    pitch index answers as one built from scratch, at every eighth of the timeline and past its
    end."""
    fresh_geometry: ScoreGeometry = ScoreGeometry(document=document)
    fresh: ScorePitch = ScorePitch(
        document=document,
        geometry=fresh_geometry,
        contexts=ContextIndex(document=document, geometry=fresh_geometry),
    )
    root: Frame = geometry.root
    points: list[Point] = [
        Point(frame=root, value=_PITCH_PROBE_STEP * number)
        for number in range(int(root.extent / _PITCH_PROBE_STEP) + _PITCH_PROBES_PAST_THE_END)
    ]
    for staff in document.staffs:
        for point in points:
            for staff_step, accidental in ((0, Accidental.NATURAL), (7, Accidental.SHARP)):
                assert _pitch_outcome(
                    index=pitch,
                    staff=staff,
                    point=point,
                    staff_step=staff_step,
                    accidental=accidental,
                ) == _pitch_outcome(
                    index=fresh,
                    staff=staff,
                    point=point,
                    staff_step=staff_step,
                    accidental=accidental,
                ), (point.value, staff_step)


def contained_ids(*, document: ScoreDocument) -> set[str]:
    """The ids of everything the document contains, read the way a record is: a score is its
    voices, staffs and measures, and a measure holds its anchors, which start the contexts and
    jumps and hold the rhythmic containers, which hold the carriers, notes and relations."""
    ids: set[str] = {entity.id for entity in (*document.voices, *document.staffs)}
    carriers: list[Carrier | None] = []
    for measure in document.measures:
        ids.add(measure.id)
        for anchor in measure.anchors:
            ids.add(anchor.id)
            ids.update(
                entity.id
                for entity in (
                    *anchor.starting_contexts,
                    *anchor.departing_jumps,
                    *anchor.arriving_jumps,
                    *anchor.containers,
                )
            )
            for container in anchor.containers:
                if not isinstance(container, LeafRhythmicContainer):
                    continue

                carriers.append(container.carrier)
                for grace in (container.grace_before, container.grace_after):
                    if grace is not None:
                        ids.add(grace.id)
                        for item in grace.grace_items:
                            ids.add(item.id)
                            carriers.append(item.carrier)

    for carrier in carriers:
        if carrier is None:
            continue

        ids.add(carrier.id)
        ids.update(relation.id for relation in carrier.carrier_group_relations)
        if isinstance(carrier, NoteCarrier):
            for item in carrier.notes:
                ids.add(item.id)
                ids.update(relation.id for relation in item.relations)
        elif isinstance(carrier, RestCarrier) and carrier.rest is not None:
            ids.add(carrier.rest.id)

    return ids


def check_entities_at_checkpoint(entities: EntityIndex, document: ScoreDocument) -> None:
    """An engine's ``checkpoint_entities_check``: at each check point of a pass the transaction's
    entity index holds exactly what the document contains, each under its own id."""
    held: Mapping[str, ScoreEntity] = entities.held()
    contained: set[str] = contained_ids(document=document)
    assert held.keys() == contained, (sorted(held.keys() ^ contained), len(held), len(contained))
    assert all(entity.id == entity_id for entity_id, entity in held.items())


def build_engine() -> MutationEngine:
    """The production engine, checking its live geometry, pitch index and entity index after
    every action and at each check point of a pass."""
    return production_build_engine(
        geometry_check=check_geometry_after_action,
        checkpoint_geometry_check=check_geometry_at_checkpoint,
        checkpoint_pitch_check=check_pitch_at_checkpoint,
        checkpoint_entities_check=check_entities_at_checkpoint,
    )


def broken_relations(*, score: Score) -> list[MutationRequest]:
    """The relation checks that would still change the document, each run on its own and
    rolled back at once: after any intent the guard has run them all, so none."""
    engine: MutationEngine = MutationEngine(
        handler_registry=build_handler_registry(),
        analyzer_registry=build_analyzer_registry(),
        postprocessors=[],
        guards=[],
        geometry_check=check_geometry_after_action,
        checkpoint_geometry_check=check_geometry_at_checkpoint,
    )

    broken: list[MutationRequest] = []
    for check in RelationGuard().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    ):
        log: MutationLog = engine.process(document=score.document, requests=[check])
        log.rollback()
        if log._entries:
            broken.append(check)

    return broken


def apply_intent(*, score: Score, intent: EditIntent) -> MutationLog:
    """Run one gesture.

    The intent is compiled against the score and processed at once; it leaves no relation
    broken.
    """
    log: MutationLog = build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )
    assert broken_relations(score=score) == []

    return log


def apply_intents(*, score: Score, intents: Sequence[EditIntent]) -> MutationLog:
    """Run several intents as one transaction, each compiled against what the one before
    left; together they leave no relation broken."""
    log: MutationLog = MutationEditor(compiler=build_compiler(), engine=build_engine()).apply(
        document=score.document,
        intents=intents,
    )
    assert broken_relations(score=score) == []

    return log


def insert_note(
    *,
    score: Score,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    dots: int = 0,
    step: int = NEW_STEP,
    beam_share: Fraction = DEFAULT_BEAM_SHARE,
) -> MutationLog:
    return apply_intent(
        score=score,
        intent=InsertNoteIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[int(at)].id,
            position=MeasurePosition.of_fraction(fraction=at - int(at)),
            written_value=value(rhythmic_value, dots),
            staff_step=step,
            accidental=Accidental.NATURAL,
            beam_share=beam_share,
        ),
    )


def delete_entities(*, score: Score, entity_ids: Sequence[str]) -> MutationLog:
    return apply_intent(score=score, intent=DeleteBatchIntent(entity_ids=tuple(entity_ids)))


def create_tuplet_with_note(
    *,
    score: Score,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
    first: DottedRhythmicValue,
    step: int = NEW_STEP,
) -> MutationLog:
    return apply_intent(
        score=score,
        intent=CreateTupletWithNoteIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[int(at)].id,
            position=MeasurePosition.of_fraction(fraction=at - int(at)),
            written_size=written,
            occupied_size=occupied,
            written_value=first,
            staff_step=step,
            accidental=Accidental.NATURAL,
        ),
    )


def note_at(*, score: Score, at: Fraction) -> Note:
    """Find the first note of the leaf starting at a timeline position."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if geometry.global_span_of(container=leaf).start == at and isinstance(carrier, NoteCarrier):
            return carrier.notes[0]

    raise LookupError(f"No note starts at {at}.")


def rest_at(*, score: Score, at: Fraction) -> Rest:
    """Find the rest of the leaf starting at a timeline position."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if (
            geometry.global_span_of(container=leaf).start == at
            and isinstance(carrier, RestCarrier)
            and carrier.rest is not None
        ):
            return carrier.rest

    raise LookupError(f"No rest starts at {at}.")


def numbered_quarters(*, score: Score, measure: int, first_step: int, count: int = 4) -> None:
    """Quarters from beat one of a measure, each on the next staff step from ``first_step``."""
    for beat in range(count):
        note(
            score=score,
            parent=score.voice,
            at=measure + Fraction(beat, 4),
            rhythmic_value=RhythmicValue.QUARTER,
            step=first_step + beat,
        )


def find_tie(*, note_with_tie: Note) -> Tie:
    """The tie a note starts or ends."""
    for relation in note_with_tie.relations:
        if isinstance(relation, Tie):
            return relation

    raise LookupError("The note has no tie.")


# The plan of editing intents (kb/progress/plan-intents.md): each agreed intent with the stage
# that implements it. A test of a stage not completed yet is a strict xfail that only the
# seam's own error satisfies; raise COMPLETED_STAGE as each stage lands.

COMPLETED_STAGE: int = 6

PLANNED_INTENTS: dict[str, int] = {
    "InsertRestIntent": 2,
    "SetFingeringIntent": 3,
    "SetArticulationIntent": 3,
    "ChangeDurationIntent": 4,
    "AppendMeasureIntent": 5,
    "InsertMeasureIntent": 5,
    "RemoveMeasureIntent": 5,
    "ChangeTimeSignatureIntent": 6,
}

_STAGE_WORK: dict[int, str] = {
    2: "InsertRest and DeleteBatch of any entity",
    3: "SetFingering / SetArticulation",
    4: "ChangeDuration",
    5: "measure operations, the tuplet split and the relation and context rules",
    6: "ChangeTimeSignature on the selection",
}


class IntentNotImplementedError(LookupError):
    """An intent the plan has agreed on is not in the compiler yet."""


def pending(*, stage: int) -> pytest.MarkDecorator:
    """Mark a test of a plan stage: a strict xfail on the seam's error until it lands."""
    return pytest.mark.xfail(
        stage > COMPLETED_STAGE,
        strict=True,
        raises=IntentNotImplementedError,
        reason=f"stage {stage} of plan-intents: {_STAGE_WORK[stage]} missing",
    )


def planned_intent(name: str, **fields: object) -> EditIntent:
    """Build a planned intent by its class name from the compiler's intents package.

    Fails inside the test, not at import, while the class does not exist yet. A name
    outside the plan raises ``KeyError``, so a misspelled name never passes as pending.
    """
    stage: int = PLANNED_INTENTS[name]
    intent_type: object = getattr(compiler_intents, name, None)
    if intent_type is None:
        raise IntentNotImplementedError(f"{name} (stage {stage}) is not in the compiler yet.")

    intent: object = cast(Callable[..., object], intent_type)(**fields)
    if not isinstance(intent, EditIntent):
        raise TypeError(f"{name} is not an edit intent.")

    return intent


def refresh_score(*, score: Score) -> Score:
    """See the same score through the document's current measures.

    After a measure is added or removed the list a scene was built with is stale.
    """
    return Score(
        document=score.document,
        voice=score.voice,
        staff=score.staff,
        measures=list(score.document.measures),
        start_context_ids=score.start_context_ids,
    )


def signatures(*, score: Score) -> list[Fraction]:
    """Every measure's time signature as its length, in measure order."""
    return [measure.time_signature.fraction for measure in score.document.measures]


type ContextSlot = tuple[str, tuple[int, Fraction], tuple[int, Fraction] | None]


def context_layout(*, score: Score) -> list[ContextSlot]:
    """Every context of the score as (kind, start, end).

    Each end is (measure index, position), (number of measures, 0) for a span that lasts until the
    end of the score; a point context has no end.
    """
    slots: list[ContextSlot] = []
    for index, measure in enumerate(score.measures):
        for anchor in measure.anchors:
            for context in anchor.starting_contexts:
                if context.id in score.start_context_ids:
                    continue

                end: tuple[int, Fraction] | None = None
                if isinstance(context, SpanContext):
                    # no end: lasts until the end of the score, the place after the last
                    end = (
                        (len(score.measures), Fraction(0))
                        if context.end is None
                        else (score.measures.index(context.end.measure), context.end.position.value)
                    )
                slots.append((type(context).__name__, (index, anchor.position.value), end))

    # the order of contexts sharing an anchor is not part of the contract
    return sorted(slots, key=lambda slot: (slot[1], slot[0]))


type GroupSpan = tuple[int, Fraction, Fraction, Fraction, int]


def group_spans(*, score: Score) -> list[GroupSpan]:
    """Every group as (measure index, position, written, occupied, depth), sizes as lengths.

    For groups whose written spelling is not fixed (a split tuplet).
    """
    return [
        (
            entry.measure_index,
            entry.position,
            entry.written.fraction,
            entry.occupied.fraction,
            entry.depth,
        )
        for entry in group_layout(score=score)
    ]


def anchor_layout(*, score: Score) -> list[tuple[int, Fraction]]:
    """Every anchor as (measure index, position), in timeline order."""
    return sorted(
        (index, anchor.position.value)
        for index, measure in enumerate(score.measures)
        for anchor in measure.anchors
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupSlot:
    """A group reduced to where it starts, its sizes and its depth (0 = in the voice)."""

    measure_index: int
    position: Fraction
    written: RhythmicSize
    occupied: RhythmicSize
    depth: int


def group_layout(*, score: Score) -> list[GroupSlot]:
    """Every group of the voice, outer before inner, in timeline order."""
    slots: list[GroupSlot] = []
    pending: list[RhythmicContainer] = list(reversed(score.voice.children))
    while pending:
        container: RhythmicContainer = pending.pop()
        if isinstance(container, GroupRhythmicContainer):
            slots.append(
                GroupSlot(
                    measure_index=score.measures.index(container.start_anchor.measure),
                    position=container.start_anchor.position.value,
                    written=container.written_size,
                    occupied=container.occupied_size,
                    depth=_depth(container=container),
                )
            )
            pending.extend(reversed(container.children))

    return slots


@dataclass(frozen=True, slots=True, kw_only=True)
class TieSlot:
    """A tie by the leaves of its two notes and their staff steps.

    Each end is (measure index, position, staff step); unlike ``tie_pairs``, two chains on
    the same pitch stay apart.
    """

    start: tuple[int, Fraction, int]
    end: tuple[int, Fraction, int]


def tie_layout(*, score: Score) -> list[TieSlot]:
    """Every tie of the voice, ordered by its start and then its end."""
    ties: list[TieSlot] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if not isinstance(carrier, NoteCarrier):
            continue
        for item in carrier.notes:
            for relation in item.relations:
                if isinstance(relation, Tie) and relation.start is item:
                    end_leaf: CarrierOwner = relation.end.note_carrier.owner
                    if not isinstance(end_leaf, LeafRhythmicContainer):
                        raise TypeError("A tied note must be held by a leaf.")
                    ties.append(
                        TieSlot(
                            start=(
                                score.measures.index(leaf.anchor.measure),
                                leaf.anchor.position.value,
                                item.staff_step,
                            ),
                            end=(
                                score.measures.index(end_leaf.anchor.measure),
                                end_leaf.anchor.position.value,
                                relation.end.staff_step,
                            ),
                        )
                    )

    return sorted(ties, key=lambda tie: (tie.start, tie.end))


type Snapshot = tuple[list[Slot], list[GroupSlot], list[TieSlot], list[tuple[int, Fraction]]]


def snapshot(*, score: Score) -> Snapshot:
    """The voice's leaves, groups and ties and every anchor of the score — what a refused
    gesture must leave exactly as it found."""
    return (
        layout(score=score),
        group_layout(score=score),
        tie_layout(score=score),
        anchor_layout(score=score),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Shape:
    """A score with rest spelling left out.

    Groups, note leaves and ties are kept exactly; rests become the merged
    ``(start, end, depth)`` stretches of the timeline they cover at each depth.
    """

    groups: list[GroupSlot]
    notes: list[Slot]
    ties: list[TieSlot]
    rests: list[tuple[Fraction, Fraction, int]]


def shape(*, score: Score) -> Shape:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    rests: list[tuple[Fraction, Fraction, int]] = []
    for leaf in iter_leaves(score.voice):
        if not isinstance(leaf.carrier, RestCarrier):
            continue
        span: Span = geometry.global_span_of(container=leaf)
        depth: int = _depth(container=leaf)
        if rests and rests[-1][1] == span.start and rests[-1][2] == depth:
            rests[-1] = (rests[-1][0], span.start + span.length, depth)
        else:
            rests.append((span.start, span.start + span.length, depth))

    return Shape(
        groups=group_layout(score=score),
        notes=[entry for entry in layout(score=score) if entry.content != "rest"],
        ties=tie_layout(score=score),
        rests=rests,
    )


# far closer to a barline than any written value: probes the instant just before it
_JUST_BEFORE: Fraction = Fraction(1, 10**6)

type _Reading = list[tuple[str, object]]
type _Questions = list[tuple[str, Callable[[], object]]]

# what geometry itself raises for a reading that has no answer
_GEOMETRY_ERRORS: tuple[type[Exception], ...] = (
    FrameMismatchError,
    OutsideFrameError,
    UnreachableFrameError,
)


def _probes(*, document: ScoreDocument) -> list[Fraction]:
    """The instants ``measure_at`` is asked about: every barline, just before it, and past
    the end — taken from the model, so a stale geometry is probed at the live instants."""
    barlines: list[Fraction] = [Fraction(0)]
    for measure in document.measures:
        barlines.append(barlines[-1] + measure.time_signature.fraction)

    probes: list[Fraction] = []
    for barline in [*barlines, barlines[-1] + 1]:
        for value in (barline - _JUST_BEFORE, barline):
            if value >= 0:
                probes.append(value)

    return probes


def _walk(*, voice: Voice) -> tuple[list[Voice | GroupRhythmicContainer], list[RhythmicContainer]]:
    """Every scope of the voice and every container in it, outer before inner, in order."""
    scopes: list[Voice | GroupRhythmicContainer] = [voice]
    containers: list[RhythmicContainer] = []
    pending: list[RhythmicContainer] = list(reversed(voice.children))
    while pending:
        container: RhythmicContainer = pending.pop()
        containers.append(container)
        if isinstance(container, GroupRhythmicContainer):
            scopes.append(container)
            pending.extend(reversed(container.children))

    return scopes, containers


def _frame_reading(*, frame: Frame) -> tuple[Transform, Fraction]:
    """A frame by its numbers: equal frames compare equal whatever index they read."""
    return frame.to_parent, frame.extent


def _geometry_questions(*, geometry: ScoreGeometry, document: ScoreDocument) -> _Questions:
    """Every question the geometry answers about the document, labelled, each asked only
    when called, in an order set by the document alone so that two geometries' questions
    line up."""
    questions: _Questions = [
        ("extent", lambda: geometry.root.extent),
        ("measure regions", geometry.measure_regions),
    ]

    for index, measure in enumerate(document.measures):
        questions.append(
            (
                f"measure {index} frame",
                partial(_frame_reading, frame=geometry.of_measure(measure=measure)),
            )
        )

    for value in _probes(document=document):
        point: Point = Point(frame=geometry.root, value=value)
        questions.append((f"measure at {value}", partial(geometry.measure_at, point=point)))

    for voice_index, voice in enumerate(document.voices):
        scopes, containers = _walk(voice=voice)

        for scope_index, scope in enumerate(scopes):
            label: str = f"voice {voice_index} scope {scope_index}"
            frame: Frame = geometry.of_scope(scope=scope)
            whole: Span = interior(frame=frame)
            questions.append((f"{label} frame", partial(_frame_reading, frame=frame)))
            questions.append((f"{label} contents", partial(geometry.contents_of, scope=scope)))
            questions.append(
                (f"{label} meets", partial(geometry.intersecting, span=whole, scope=scope))
            )
            questions.append((f"{label} slices", partial(geometry.slice_by_measures, span=whole)))
            for index, measure in enumerate(document.measures):
                questions.append(
                    (
                        f"{label} contents in measure {index}",
                        partial(geometry.contents_in, scope=scope, measure=measure),
                    )
                )

        for container_index, container in enumerate(containers):
            label = f"voice {voice_index} container {container_index}"
            questions.append((f"{label} span", partial(geometry.span_of, container=container)))
            questions.append(
                (f"{label} global span", partial(geometry.global_span_of, container=container))
            )
            questions.append(
                (
                    f"{label} containing frame",
                    partial(
                        _frame_reading,
                        frame=geometry.of_scope(scope=container.parent),
                    ),
                )
            )
            if isinstance(container, GroupRhythmicContainer):
                questions.append(
                    (
                        f"{label} frame",
                        partial(_frame_reading, frame=geometry.of_group(group=container)),
                    )
                )

        for index, measure in enumerate(document.measures):
            for anchor in measure.anchors:
                label = f"voice {voice_index} anchor {index}+{anchor.position.value}"
                point = geometry.point_of(anchor=anchor)
                questions.append((f"{label} point", partial(geometry.point_of, anchor=anchor)))
                questions.append(
                    (
                        f"{label} deepest scope",
                        partial(geometry.deepest_scope_at, point=point, voice=voice),
                    )
                )

    return questions


def _reference_measure_start(*, measure: Measure) -> Fraction:
    """Where the measure begins, from the model alone: every measure before it, summed."""
    start: Fraction = Fraction(0)
    previous: Measure | None = measure.prev_measure
    while previous is not None:
        start += previous.time_signature.fraction
        previous = previous.prev_measure

    return start


def _reference_position(*, anchor: TemporalAnchor, starts: dict[Measure, Fraction]) -> Fraction:
    return starts[anchor.measure] + anchor.position.value


def _reference_offset(
    *,
    container: RhythmicContainer,
    starts: dict[Measure, Fraction],
) -> Fraction:
    """Where the container begins in its parent's frame, from the model alone: its anchor on
    the timeline, restated down through every enclosing group one step at a time."""
    groups: list[GroupRhythmicContainer] = []
    parent: RhythmicContainerParent = container.parent
    while isinstance(parent, GroupRhythmicContainer):
        groups.insert(0, parent)
        parent = parent.parent

    offset: Fraction = _reference_position(anchor=container.start_anchor, starts=starts)
    for group in groups:
        offset = (
            (offset - _reference_offset(container=group, starts=starts))
            * group.written_size.fraction
            / group.occupied_size.fraction
        )

    return offset


def _reference_length(*, container: RhythmicContainer) -> Fraction:
    """How long the container lasts on the timeline: its room squeezed by every enclosing
    group."""
    length: Fraction = container.occupied_size.fraction
    parent: RhythmicContainerParent = container.parent
    while isinstance(parent, GroupRhythmicContainer):
        length = length * parent.occupied_size.fraction / parent.written_size.fraction
        parent = parent.parent

    return length


def _reference_reading(*, document: ScoreDocument) -> _Reading:
    """What the geometry should answer, worked out from the model alone the stateless way —
    labelled as ``_numbers_reading`` labels the geometry's answers."""
    starts: dict[Measure, Fraction] = {
        measure: _reference_measure_start(measure=measure) for measure in document.measures
    }
    regions: list[tuple[Measure, Fraction, Fraction]] = [
        (measure, starts[measure], measure.time_signature.fraction) for measure in document.measures
    ]
    reading: _Reading = [
        ("extent", sum((length for _, _, length in regions), Fraction(0))),
        ("measure regions", regions),
    ]

    for value in _probes(document=document):
        found: Measure | None = next(
            (measure for measure, start, length in regions if start <= value < start + length),
            None,
        )
        reading.append((f"measure at {value}", found))

    for voice_index, voice in enumerate(document.voices):
        scopes, containers = _walk(voice=voice)

        for scope_index, scope in enumerate(scopes):
            for index, (_, measure_start, measure_length) in enumerate(regions):
                reaching: list[RhythmicContainer] = [
                    child
                    for child in scope.children
                    if _reference_position(anchor=child.start_anchor, starts=starts)
                    < measure_start + measure_length
                    and measure_start
                    < _reference_position(anchor=child.start_anchor, starts=starts)
                    + _reference_length(container=child)
                ]
                reading.append(
                    (f"voice {voice_index} scope {scope_index} in measure {index}", reaching)
                )

        for container_index, container in enumerate(containers):
            label: str = f"voice {voice_index} container {container_index}"
            reading.append(
                (
                    f"{label} span",
                    (
                        _reference_offset(container=container, starts=starts),
                        container.occupied_size.fraction,
                    ),
                )
            )
            reading.append(
                (
                    f"{label} global span",
                    (
                        _reference_position(anchor=container.start_anchor, starts=starts),
                        _reference_length(container=container),
                    ),
                )
            )
            if isinstance(container, GroupRhythmicContainer):
                reading.append(
                    (
                        f"{label} frame",
                        (
                            container.occupied_size.fraction / container.written_size.fraction,
                            _reference_offset(container=container, starts=starts),
                            container.written_size.fraction,
                        ),
                    )
                )

        for index, measure in enumerate(document.measures):
            for anchor in measure.anchors:
                reading.append(
                    (
                        f"voice {voice_index} anchor {index}+{anchor.position.value}",
                        _reference_position(anchor=anchor, starts=starts),
                    )
                )

    return reading


def _numbers_reading(*, geometry: ScoreGeometry, document: ScoreDocument) -> _Reading:
    """The geometry's answers as plain numbers and entities, labelled as
    ``_reference_reading`` labels what they should be."""
    regions: list[tuple[Measure, Fraction, Fraction]] = [
        (measure, region.start, region.length) for measure, region in geometry.measure_regions()
    ]
    reading: _Reading = [("extent", geometry.root.extent), ("measure regions", regions)]

    for value in _probes(document=document):
        point: Point = Point(frame=geometry.root, value=value)
        reading.append((f"measure at {value}", geometry.measure_at(point=point)))

    for voice_index, voice in enumerate(document.voices):
        scopes, containers = _walk(voice=voice)

        for scope_index, scope in enumerate(scopes):
            for index, measure in enumerate(document.measures):
                reading.append(
                    (
                        f"voice {voice_index} scope {scope_index} in measure {index}",
                        [child for child, _ in geometry.contents_in(scope=scope, measure=measure)],
                    )
                )

        for container_index, container in enumerate(containers):
            label: str = f"voice {voice_index} container {container_index}"
            span: Span = geometry.span_of(container=container)
            reach: Span = geometry.global_span_of(container=container)
            reading.append((f"{label} span", (span.start, span.length)))
            reading.append((f"{label} global span", (reach.start, reach.length)))
            if isinstance(container, GroupRhythmicContainer):
                frame: Frame = geometry.of_group(group=container)
                reading.append(
                    (
                        f"{label} frame",
                        (frame.to_parent.scale, frame.to_parent.offset, frame.extent),
                    )
                )

        for index, measure in enumerate(document.measures):
            for anchor in measure.anchors:
                reading.append(
                    (
                        f"voice {voice_index} anchor {index}+{anchor.position.value}",
                        geometry.point_of(anchor=anchor).value,
                    )
                )

    return reading


def geometry_differences(*, geometry: ScoreGeometry, document: ScoreDocument) -> list[str]:
    """What ``geometry`` answers differently from a geometry built from scratch on the same
    document, or from the model read directly the stateless way, over every measure, scope,
    container and anchor; empty when it agrees with both."""
    fresh: _Questions = _geometry_questions(
        geometry=ScoreGeometry(document=document),
        document=document,
    )
    live: _Questions = _geometry_questions(geometry=geometry, document=document)
    differences: list[str] = [
        label
        for (label, expected), (_, actual) in zip(fresh, live, strict=True)
        if actual() != expected()
    ]

    reference: _Reading = _reference_reading(document=document)
    numbers: _Reading = _numbers_reading(geometry=geometry, document=document)
    for (label, expected_number), (_, actual_number) in zip(reference, numbers, strict=True):
        if actual_number != expected_number:
            differences.append(f"{label}, against the model")

    return differences


def transient_geometry_differences(
    *,
    geometry: ScoreGeometry,
    document: ScoreDocument,
) -> list[str]:
    """What ``geometry`` answers differently from a geometry built from scratch, on a
    document that may be caught in the middle of an edit; empty when they agree.

    Mid-edit a question may have no answer — an anchor moved before its group follows. A
    question the fresh build answers with one of geometry's errors must raise the same
    error live, and is then skipped. The model is not read: it holds no answer either.
    """
    fresh: _Questions = _geometry_questions(
        geometry=ScoreGeometry(document=document),
        document=document,
    )
    live: _Questions = _geometry_questions(geometry=geometry, document=document)

    differences: list[str] = []
    for (label, expected), (_, actual) in zip(fresh, live, strict=True):
        answer: object = None
        unanswered: Exception | None = None
        try:
            answer = expected()
        except _GEOMETRY_ERRORS as error:
            unanswered = error

        try:
            live_answer: object = actual()
        except KeyError as error:
            # an entity the live index never indexed: a change not delivered. Named by type
            # only, since an entity's repr walks the whole score and would never finish.
            differences.append(f"{label}, a {type(error.args[0]).__name__} never indexed live")
            continue
        except _GEOMETRY_ERRORS as error:
            if type(error) is not type(unanswered):
                differences.append(f"{label}, raises {error!r} live, not {unanswered!r}")
            continue

        if unanswered is not None:
            differences.append(f"{label}, answered live where a fresh build raises {unanswered!r}")
        elif live_answer != answer:
            differences.append(label)

    return differences


type Scene = Callable[[], Score]


def four_quarters() -> Score:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    return score


def triplet_scene() -> Score:
    """Build a quarter, an eighth triplet on beat two (staff steps 1, 2, 3), two quarters."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=Fraction(1, 4))
    quarters(score=score, measure=0, beats=(2, 3))

    return score


def crossing_half() -> Score:
    """Build quarters on beats 1-3 and a half on beat 4 (staff step 1) stored as q~q.

    The half crosses the barline; the rest of measure 2 is a rest.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF, step=1)

    return score


def crossing_triplet() -> Score:
    """Build two measures of quarters with a quarter triplet sounding [3/4, 5/4).

    The triplet holds q (step 1) at 3/4, q (step 2) at 11/12 stored as e~e across the
    barline, and q (step 3) at 13/12.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    create_tuplet_with_note(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
        step=1,
    )
    insert_note(score=score, at=Fraction(11, 12), rhythmic_value=RhythmicValue.QUARTER, step=2)
    insert_note(score=score, at=Fraction(13, 12), rhythmic_value=RhythmicValue.QUARTER, step=3)

    return score
