from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.application.ports.importing import (
    ImportIssue,
    ImportRefusedError,
    IssueKind,
    SourceClef,
    SourceKey,
    SourceMeasure,
    SourceScore,
)
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    GracePlacement,
    GraceType,
    RhythmicSize,
)
from piano_app.domain.score.document.models.presentation import PresentationTarget, ReferencePoint
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers.grace_time import SLASHED_SCALE, fits
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation import (
    MutationCompiler,
    MutationEngine,
    MutationTransaction,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
    InsertNoteIntent,
    InsertRestIntent,
    PitchEditMode,
    SetClefIntent,
    SetKeySignatureIntent,
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests import (
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateBeamRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.presentation import (
    PresentationCommand,
    PresentationEditor,
    SetDirection,
)

from .lookup import LeafKey, NoteKey, leaf_index, note_index
from .mappings import (
    alterations_of,
    clef_of,
    midi_of,
    size_of_length,
    time_signature_of,
)
from .marks import MarkPlacer
from .plan import STAFF_COUNT, Entry, GraceEntry, Plan, ScorePlanner, TiePair

DEFAULT_VOICE_COUNT: int = 4

_QUARTERS_PER_WHOLE: int = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class BuiltScore:
    document: ScoreDocument
    issues: tuple[ImportIssue, ...]


class ScoreBuilder:
    """Builds a score from the source score through the mutation engine.

    The document is made with its measures at their own lengths (the engine would re-bar a time
    signature change and add a measure). The octave lines go in first, since they say how the
    pitch of a note is written. In one transaction the clefs and keys go in as one pass;
    then the notes and rests, a pass for each place in a chord and in a tuplet (a note is compiled
    against the score as the pass before it left it); then the ties between notes that exist by
    then; then the grace notes, a pass for each, one after another on every note they belong to.
    Whatever the score has no place for is left out and goes into the issues of the result.
    """

    def __init__(self, *, engine: MutationEngine, compiler: MutationCompiler) -> None:
        self._engine: MutationEngine = engine
        self._compiler: MutationCompiler = compiler
        self._planner: ScorePlanner = ScorePlanner()
        self._marks: MarkPlacer = MarkPlacer(engine=engine, compiler=compiler)

    def build(self, *, source: SourceScore) -> BuiltScore:
        issues: list[ImportIssue] = list(source.issues)
        voice_numbers: list[int] = sorted({note.voice for m in source.measures for note in m.notes})
        document: ScoreDocument = ScoreDocument.create(
            voices=[Voice() for _ in range(max(DEFAULT_VOICE_COUNT, len(voice_numbers)))],
            staffs=[Staff() for _ in range(STAFF_COUNT)],
            measures=[
                self._measure_of(source_measure=measure, issues=issues)
                for measure in source.measures
            ],
        )
        document.place_start_contexts()

        try:
            self._marks.place_octave_lines(document=document, source=source, issues=issues)
            with self._engine.transaction(document=document) as transaction:
                self._set_clefs_and_keys(
                    transaction=transaction, document=document, source=source, issues=issues
                )
                plan: Plan = self._planner.plan(
                    document=document, source=source, voice_numbers=voice_numbers, issues=issues
                )
                self._insert(transaction=transaction, document=document, plan=plan)
                self._tie(
                    transaction=transaction,
                    document=document,
                    ties=plan.ties,
                    source=source,
                    issues=issues,
                )
                self._beam(transaction=transaction, document=document, plan=plan)
                self._grace(
                    transaction=transaction,
                    document=document,
                    plan=plan,
                    source=source,
                    issues=issues,
                )
                self._stems(transaction=transaction, document=document, plan=plan)
        except MutationRejectedError as error:
            if "Cannot spell" in str(error):
                raise ImportRefusedError(
                    reason="A stretch of time in the score cannot be written as notes or rests "
                    "(a tuplet or a very short note that is not imported leaves it); "
                    "such a file is not supported yet."
                ) from error

            raise ImportRefusedError(reason=f"The score could not be built: {error}") from error

        self._marks.place_contexts(
            document=document, source=source, voice_numbers=voice_numbers, issues=issues
        )
        self._marks.place_marks(
            document=document, source=source, voice_numbers=voice_numbers, issues=issues
        )

        return BuiltScore(document=document, issues=tuple(issues))

    def _measure_of(self, *, source_measure: SourceMeasure, issues: list[ImportIssue]) -> Measure:
        size: RhythmicSize | None = time_signature_of(time=source_measure.time)
        if size is None:
            raise ImportRefusedError(
                reason=f"A time signature in {source_measure.time.beat_type}ths is not supported."
            )

        full: Fraction = size.fraction * _QUARTERS_PER_WHOLE
        if source_measure.is_implicit and 0 < source_measure.extent < full:
            pickup: RhythmicSize | None = size_of_length(quarters=source_measure.extent)
            if pickup is None:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.CHANGED,
                        measure=source_measure.number,
                        message="A partial measure of this length is kept at the full length.",
                    )
                )
            else:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.CHANGED,
                        measure=source_measure.number,
                        message="A pickup measure got a time signature of its own.",
                    )
                )
                size = pickup

        return Measure.create(time_signature=size)

    def _set_clefs_and_keys(
        self,
        *,
        transaction: MutationTransaction,
        document: ScoreDocument,
        source: SourceScore,
        issues: list[ImportIssue],
    ) -> None:
        requests: list[MutationRequest] = []
        fifths: int = 0
        clefs: dict[int, tuple[Clef, int]] = {1: (Clef.TREBLE, 0), 2: (Clef.BASS, 0)}

        for index, source_measure in enumerate(source.measures):
            measure: Measure = document.measures[index]
            for key in source_measure.keys:
                if key.fifths == fifths:
                    continue

                if self._key_requests(
                    entities=transaction.entities,
                    document=document,
                    measure=measure,
                    key=key,
                    requests=requests,
                    number=source_measure.number,
                    issues=issues,
                ):
                    fifths = key.fifths

            for clef in source_measure.clefs:
                self._clef_requests(
                    entities=transaction.entities,
                    document=document,
                    measure=measure,
                    clef=clef,
                    current=clefs,
                    requests=requests,
                    number=source_measure.number,
                    issues=issues,
                )

        if requests:
            transaction.run(requests=requests)

    def _key_requests(
        self,
        *,
        entities: EntityIndex,
        document: ScoreDocument,
        measure: Measure,
        key: SourceKey,
        requests: list[MutationRequest],
        number: str,
        issues: list[ImportIssue],
    ) -> bool:
        alterations: tuple[Accidental, ...] | None = alterations_of(fifths=key.fifths)
        if alterations is None:
            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    message="A key signature of more than seven accidentals is not imported.",
                )
            )
            return False

        for staff in document.staffs:
            requests.extend(
                self._compiler.compile(
                    document=document,
                    intent=SetKeySignatureIntent(
                        staff_id=staff.id,
                        measure_id=measure.id,
                        position=_position(quarters=key.onset),
                        alterations=alterations,
                    ),
                    entities=entities,
                )
            )

        return True

    def _clef_requests(
        self,
        *,
        entities: EntityIndex,
        document: ScoreDocument,
        measure: Measure,
        clef: SourceClef,
        current: dict[int, tuple[Clef, int]],
        requests: list[MutationRequest],
        number: str,
        issues: list[ImportIssue],
    ) -> None:
        mapped: tuple[Clef, int] | None = clef_of(clef=clef)
        if mapped is None or clef.staff not in current:
            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    message=f"The {clef.sign} clef on staff {clef.staff} is not imported.",
                )
            )
            return

        if mapped == current[clef.staff]:
            return

        current[clef.staff] = mapped
        requests.extend(
            self._compiler.compile(
                document=document,
                intent=SetClefIntent(
                    staff_id=document.staffs[clef.staff - 1].id,
                    measure_id=measure.id,
                    position=_position(quarters=clef.onset),
                    clef=mapped[0],
                    octave_transposition=mapped[1],
                    mode=PitchEditMode.PRESERVE_STEP,
                ),
                entities=entities,
            )
        )

    def _insert(
        self,
        *,
        transaction: MutationTransaction,
        document: ScoreDocument,
        plan: Plan,
    ) -> None:
        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
        starts: list[Fraction] = _measure_starts(document=document)

        for layer in sorted(plan.layers):
            requests: list[MutationRequest] = []
            for entry in plan.layers[layer]:
                requests.extend(
                    self._compile_entry(
                        entities=transaction.entities,
                        document=document,
                        entry=entry,
                        start=starts[entry.measure_index],
                        geometry=geometry,
                        pitch=pitch,
                    )
                )

            transaction.run(requests=requests)

    def _compile_entry(
        self,
        *,
        entities: EntityIndex,
        document: ScoreDocument,
        entry: Entry,
        start: Fraction,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> Sequence[MutationRequest]:
        measure: Measure = document.measures[entry.measure_index]
        voice: Voice = document.voices[entry.voice_index]
        staff: Staff = document.staffs[entry.note.staff - 1]
        position: MeasurePosition = _position(quarters=entry.note.onset)

        if entry.note.pitch is None or entry.accidental is None:
            if entry.tuplet is not None:
                return self._compiler.compile(
                    document=document,
                    intent=CreateTupletWithRestIntent(
                        voice_id=voice.id,
                        staff_id=staff.id,
                        measure_id=measure.id,
                        position=position,
                        written_size=entry.tuplet.written,
                        occupied_size=entry.tuplet.occupied,
                        written_value=entry.value,
                    ),
                    entities=entities,
                )

            return self._compiler.compile(
                document=document,
                intent=InsertRestIntent(
                    voice_id=voice.id,
                    staff_id=staff.id,
                    measure_id=measure.id,
                    position=position,
                    written_value=entry.value,
                ),
                entities=entities,
            )

        step: int = pitch.staff_step_for(
            staff=staff,
            point=Point(frame=geometry.root, value=start + position.value),
            midi_note=midi_of(pitch=entry.note.pitch),
            accidental=entry.accidental,
        )
        if entry.tuplet is not None:
            return self._compiler.compile(
                document=document,
                intent=CreateTupletWithNoteIntent(
                    voice_id=voice.id,
                    staff_id=staff.id,
                    measure_id=measure.id,
                    position=position,
                    written_size=entry.tuplet.written,
                    occupied_size=entry.tuplet.occupied,
                    written_value=entry.value,
                    staff_step=step,
                    accidental=entry.accidental,
                ),
                entities=entities,
            )

        return self._compiler.compile(
            document=document,
            intent=InsertNoteIntent(
                voice_id=voice.id,
                staff_id=staff.id,
                measure_id=measure.id,
                position=position,
                written_value=entry.value,
                staff_step=step,
                accidental=entry.accidental,
                # the beams are the file's own, made after the notes: none is grown here
                beam_share=Fraction(0),
            ),
            entities=entities,
        )

    def _beam(
        self, *, transaction: MutationTransaction, document: ScoreDocument, plan: Plan
    ) -> None:
        if not plan.beams:
            return

        leaves: dict[LeafKey, LeafRhythmicContainer] = leaf_index(document=document)
        requests: list[MutationRequest] = []
        for run in plan.beams:
            # a note that is not there cuts the run: a beam holds neighbours only
            pieces: list[list[NoteCarrier]] = [[]]
            for key in run:
                leaf: LeafRhythmicContainer | None = leaves.get(key)
                if leaf is not None and isinstance(leaf.carrier, NoteCarrier):
                    pieces[-1].append(leaf.carrier)
                else:
                    pieces.append([])

            requests.extend(
                CreateBeamRequest(carriers=tuple(piece)) for piece in pieces if len(piece) >= 2
            )

        if requests:
            transaction.run(requests=requests)

    def _stems(
        self, *, transaction: MutationTransaction, document: ScoreDocument, plan: Plan
    ) -> None:
        if not plan.stems:
            return

        leaves: dict[LeafKey, LeafRhythmicContainer] = leaf_index(document=document)
        commands: list[PresentationCommand] = []
        for key, direction in plan.stems:
            leaf: LeafRhythmicContainer | None = leaves.get(key)
            if leaf is not None and isinstance(leaf.carrier, NoteCarrier):
                commands.append(
                    SetDirection(
                        target=PresentationTarget(
                            entity_id=leaf.carrier.id, reference=ReferencePoint.STEM_TIP
                        ),
                        value=direction,
                    )
                )

        try:
            PresentationEditor().apply(document=document, commands=commands, sink=transaction.log)
        except ValueError as error:
            raise MutationRejectedError(reason=str(error)) from error

    def _tie(
        self,
        *,
        transaction: MutationTransaction,
        document: ScoreDocument,
        ties: list[TiePair],
        source: SourceScore,
        issues: list[ImportIssue],
    ) -> None:
        if not ties:
            return

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
        notes: dict[NoteKey, Note] = note_index(document=document, pitch=pitch)
        requests: list[MutationRequest] = []

        for pair in ties:
            start: Note | None = notes.get(pair.start)
            end: Note | None = notes.get(pair.end)
            if start is None or end is None:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=source.measures[pair.start[2]].number,
                        message="A tie to a note that could not be found is not imported.",
                    )
                )
                continue

            requests.extend(
                self._compiler.compile(
                    document=document,
                    intent=TieNotesIntent(start_note_id=start.id, end_note_id=end.id),
                    entities=transaction.entities,
                )
            )

        if requests:
            transaction.run(requests=requests)

    def _grace(
        self,
        *,
        transaction: MutationTransaction,
        document: ScoreDocument,
        plan: Plan,
        source: SourceScore,
        issues: list[ImportIssue],
    ) -> None:
        if not plan.graces:
            return

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
        leaves: dict[LeafKey, LeafRhythmicContainer] = leaf_index(document=document)
        starts: list[Fraction] = _measure_starts(document=document)

        for step in sorted(plan.graces):
            requests: list[MutationRequest] = []
            for grace in plan.graces[step]:
                leaf: LeafRhythmicContainer | None = leaves.get(
                    (grace.host_voice, grace.host_measure, grace.host_position)
                )
                intent: AddGraceNoteIntent | AddGraceCarrierNoteIntent | None = self._grace_intent(
                    document=document,
                    grace=grace,
                    leaf=leaf,
                    start=starts[grace.host_measure],
                    geometry=geometry,
                    pitch=pitch,
                )
                if intent is None:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=source.measures[grace.host_measure].number,
                            message="A grace note that does not fit the note it belongs to "
                            "is not imported.",
                        )
                    )
                    continue

                requests.extend(
                    self._compiler.compile(
                        document=document, intent=intent, entities=transaction.entities
                    )
                )

            if requests:
                transaction.run(requests=requests)

    def _grace_intent(
        self,
        *,
        document: ScoreDocument,
        grace: GraceEntry,
        leaf: LeafRhythmicContainer | None,
        start: Fraction,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> AddGraceNoteIntent | AddGraceCarrierNoteIntent | None:
        """The request that puts the grace note in, or ``None`` when its note or its item is not
        there, or when the time it would take does not fit."""
        if leaf is None or leaf.carrier is None or grace.note.pitch is None:
            return None

        group: GraceGroup | None = (
            leaf.grace_before if grace.placement is GracePlacement.BEFORE else leaf.grace_after
        )
        staff: Staff = document.staffs[grace.note.staff - 1]
        staff_step: int = pitch.staff_step_for(
            staff=staff,
            point=Point(frame=geometry.root, value=start + grace.host_position),
            midi_note=midi_of(pitch=grace.note.pitch),
            accidental=grace.accidental,
        )

        if not grace.is_lead:
            if group is None or grace.item_index >= len(group.grace_items):
                return None

            carrier = group.grace_items[grace.item_index].carrier
            if carrier is None:
                return None

            return AddGraceCarrierNoteIntent(
                carrier_id=carrier.id,
                staff_id=staff.id,
                staff_step=staff_step,
                accidental=grace.accidental,
            )

        after_id: str | None = None
        if grace.item_index > 0:
            if group is None or grace.item_index > len(group.grace_items):
                return None

            previous = group.grace_items[grace.item_index - 1].carrier
            if previous is None:
                return None

            after_id = previous.id

        written: Fraction = grace.value.fraction
        sounding: Fraction = written * SLASHED_SCALE if grace.note.is_slashed else written
        if not fits(leaf=leaf, length=leaf.written_size.fraction, extra=sounding):
            return None

        return AddGraceNoteIntent(
            host_carrier_id=leaf.carrier.id,
            placement=grace.placement,
            grace_type=GraceType.ACCIACCATURA if grace.note.is_slashed else GraceType.APPOGGIATURA,
            written_value=grace.value,
            staff_id=staff.id,
            staff_step=staff_step,
            accidental=grace.accidental,
            after_carrier_id=after_id,
        )


def _measure_starts(*, document: ScoreDocument) -> list[Fraction]:
    starts: list[Fraction] = []
    offset: Fraction = Fraction(0)
    for measure in document.measures:
        starts.append(offset)
        offset += measure.time_signature.fraction

    return starts


def _position(*, quarters: Fraction) -> MeasurePosition:
    whole_notes: Fraction = quarters / _QUARTERS_PER_WHOLE

    return MeasurePosition.of(numerator=whole_notes.numerator, denominator=whole_notes.denominator)
