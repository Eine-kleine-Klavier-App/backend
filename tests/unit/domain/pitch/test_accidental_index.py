from fractions import Fraction
from random import Random

import pytest

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, KeySignatureChange
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceNoteIntent,
    DeleteBatchIntent,
    EditIntent,
    InsertMeasureIntent,
    InsertNoteIntent,
    MoveNoteToStaffIntent,
    PitchEditMode,
    RemoveGraceNoteIntent,
    SetAccidentalIntent,
)
from piano_app.domain.score.document.services.pitch import SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .test_accidental_inference import key, note

_STEPS: tuple[int, ...] = (-2, 0, 3)
_QUARTER: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)


def _walk(
    *, document: ScoreDocument, staff_index: int, at: Fraction, step: int, cell: SignCell
) -> Accidental:
    """The answer by walking the measure's anchors, independent of the index: of the notes on the
    step that stand up to and including the cell at the point, the last place; at a note cell the
    first note stands, at a grace cell the last one; else the key."""
    geometry = ScoreGeometry(document=document)
    contexts = ContextIndex(document=document, geometry=geometry)
    staff = document.staffs[staff_index]
    measure = geometry.measure_at(point=Point(frame=geometry.root, value=at))
    assert measure is not None
    local = at - geometry.measure_span(measure=measure).start
    standing: list[tuple[tuple[Fraction, SignCell], Note]] = []
    for anchor in measure.anchors:
        for container in anchor.containers:
            if not isinstance(container, LeafRhythmicContainer):
                continue

            carriers: list[tuple[SignCell, object]] = []
            if container.grace_before is not None:
                carriers += [
                    (SignCell.BEFORE, grace.carrier) for grace in container.grace_before.grace_items
                ]
            carriers.append((SignCell.NOTE, container.carrier))
            if container.grace_after is not None:
                carriers += [
                    (SignCell.AFTER, grace.carrier) for grace in container.grace_after.grace_items
                ]

            for where, carrier in carriers:
                if isinstance(carrier, NoteCarrier):
                    standing += [
                        ((anchor.position.value, where), item)
                        for item in carrier.notes
                        if item.staff is staff and item.staff_step == step
                    ]

    reached = [(place, item) for place, item in standing if place <= (local, cell)]
    if reached:
        last = max(place for place, _ in reached)
        same = [item for place, item in reached if place == last]
        return (same[0] if last[1] is SignCell.NOTE else same[-1]).accidental

    return _key_sign(
        document=document, contexts=contexts, staff_index=staff_index, at=at, step=step
    )


def _key_sign(
    *, document: ScoreDocument, contexts: ContextIndex, staff_index: int, at: Fraction, step: int
) -> Accidental:
    scope = Scope.of_staff(staff=document.staffs[staff_index])
    signature: KeySignatureChange | None = contexts.piece_at(
        kind=KeySignatureChange, point=at, scope=scope
    ).value
    clef: ClefChange | None = contexts.piece_at(kind=ClefChange, point=at, scope=scope).value
    if signature is None:
        return Accidental.NATURAL

    assert clef is not None
    origin = {"treble": 37, "bass": 25}[clef.clef.value]
    return signature.alterations[(origin + step) % 7]


def _assert_same_as_walk(
    pitch: ScorePitch, geometry: ScoreGeometry, document: ScoreDocument
) -> None:
    extent = geometry.root.extent
    for staff_index, staff in enumerate(document.staffs):
        for eighth in range(int(extent * 8)):
            # on an anchor and between two
            for at in (Fraction(eighth, 8), Fraction(eighth, 8) + Fraction(1, 16)):
                for step in _STEPS:
                    for cell in SignCell:
                        point = Point(frame=geometry.root, value=at)
                        assert pitch.accidental_at(
                            staff=staff, point=point, staff_step=step, cell=cell
                        ) is _walk(
                            document=document, staff_index=staff_index, at=at, step=step, cell=cell
                        )


@pytest.mark.parametrize("seed", range(6))
def test_the_index_answers_as_a_walk_of_the_measure_does(seed: int) -> None:
    random = Random(seed)
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=3)
    signs = list(Accidental)
    key(document, Fraction(0), tuple(random.choice(signs[1:4]) for _ in range(7)))
    for _ in range(14):
        note(
            document,
            Fraction(random.randrange(24), 8),
            random.choice(signs),
            step=random.choice(_STEPS),
            staff=random.randrange(2),
            voice=random.randrange(2),
        )

    geometry = ScoreGeometry(document=document)
    pitch = ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )

    _assert_same_as_walk(pitch, geometry, document)


def test_a_warmed_index_follows_edits_made_through_the_engine() -> None:
    """After every step of every edit the index the engine keeps is compared with a fresh
    one and with a walk of the measure: a note inserted, given another sign, moved to the
    other staff, deleted, and a measure inserted before it all."""
    checked: list[int] = []

    def check(pitch: ScorePitch, geometry: ScoreGeometry, document: ScoreDocument) -> None:
        _assert_same_as_walk(pitch, geometry, document)
        checked.append(1)

    document = ScoreDocument.create_fresh(staff_count=2, voice_count=1, measure_count=2)
    engine = build_engine(checkpoint_pitch_check=check)
    compiler = build_compiler()

    def run(intent: EditIntent) -> None:
        engine.process(
            document=document, requests=compiler.compile(document=document, intent=intent)
        )

    def insert(position: int, *, staff: int, accidental: Accidental | None) -> None:
        run(
            InsertNoteIntent(
                voice_id=document.voices[0].id,
                staff_id=document.staffs[staff].id,
                measure_id=document.measures[0].id,
                position=MeasurePosition.of(numerator=position, denominator=4),
                written_value=_QUARTER,
                staff_step=0,
                accidental=accidental,
            )
        )

    insert(0, staff=0, accidental=Accidental.SHARP)
    insert(1, staff=0, accidental=None)
    insert(2, staff=0, accidental=Accidental.FLAT)
    notes = [
        item
        for measure in document.measures
        for anchor in measure.anchors
        for container in anchor.containers
        if isinstance(container, LeafRhythmicContainer)
        and isinstance(container.carrier, NoteCarrier)
        for item in container.carrier.notes
    ]
    assert len(notes) == 3

    def add_grace(host: Note, placement: GracePlacement, accidental: Accidental) -> None:
        run(
            AddGraceNoteIntent(
                host_carrier_id=host.note_carrier.id,
                placement=placement,
                grace_type=GraceType.APPOGGIATURA,
                written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
                staff_id=document.staffs[0].id,
                staff_step=0,
                accidental=accidental,
            )
        )

    add_grace(notes[0], GracePlacement.BEFORE, Accidental.DOUBLE_FLAT)
    add_grace(notes[1], GracePlacement.AFTER, Accidental.FLAT)
    run(SetAccidentalIntent(note_id=notes[0].id, accidental=Accidental.NATURAL))
    run(
        MoveNoteToStaffIntent(
            note_id=notes[1].id, staff_id=document.staffs[1].id, mode=PitchEditMode.PRESERVE_STEP
        )
    )
    run(DeleteBatchIntent(entity_ids=(notes[2].id,)))
    grace_before = notes[0].note_carrier.owner
    assert isinstance(grace_before, LeafRhythmicContainer) and grace_before.grace_before is not None
    grace_note = grace_before.grace_before.grace_items[0].carrier
    assert isinstance(grace_note, NoteCarrier)
    run(RemoveGraceNoteIntent(note_id=grace_note.notes[0].id))
    run(InsertMeasureIntent(before_measure_id=document.measures[0].id))

    assert len(checked) > 10
