from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score
from tests.unit.domain.pitch.test_accidental_inference import key

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    Clef,
    DottedRhythmicValue,
    Fingering,
    GracePlacement,
    GraceType,
    Ornament,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import taken_from
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    ChangeGraceValueIntent,
    ChangePitchIntent,
    EditIntent,
    MoveNoteToStaffIntent,
    PitchEditMode,
    SetAccidentalIntent,
    SetArticulationIntent,
    SetClefIntent,
    SetFingeringIntent,
    SetOrnamentIntent,
    ShiftStaffStepsIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

# Grace carriers are edited like the carriers of a note: placed anywhere in their group, joined by
# further notes, written as another value, moved in pitch, marked. Each grace note here stands on
# its own staff step, which tells the notes apart.


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _sounds(*, document: ScoreDocument, target: Note) -> int:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    return (
        ScorePitch(
            document=document,
            geometry=geometry,
            contexts=ContextIndex(document=document, geometry=geometry),
        )
        .pitch_of(note=target)
        .midi_note
    )


def _host(document: ScoreDocument) -> tuple[Note, LeafRhythmicContainer]:
    host: Note = note(document, Fraction(0))
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    return host, leaf


def _add(
    *,
    document: ScoreDocument,
    host: Note,
    step: int,
    value: RhythmicValue = RhythmicValue.SIXTEENTH,
    placement: GracePlacement = GracePlacement.BEFORE,
    after: NoteCarrier | None = None,
) -> NoteCarrier:
    """Adds a grace note on ``step`` and returns the carrier it made."""
    _run(
        document=document,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=placement,
            grace_type=GraceType.APPOGGIATURA,
            written_value=DottedRhythmicValue(value=value),
            staff_id=document.staffs[0].id,
            staff_step=step,
            accidental=Accidental.NATURAL,
            after_carrier_id=None if after is None else after.id,
        ),
    )
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    group: GraceGroup | None = (
        leaf.grace_before if placement is GracePlacement.BEFORE else leaf.grace_after
    )
    assert group is not None
    return _carrier_on(group=group, step=step)


def _carrier_on(*, group: GraceGroup, step: int) -> NoteCarrier:
    for item in group.grace_items:
        carrier = item.carrier
        assert isinstance(carrier, NoteCarrier)
        if any(grace.staff_step == step for grace in carrier.notes):
            return carrier

    raise LookupError("No grace carrier on that step.")


def _steps(*, group: GraceGroup | None) -> list[list[int]]:
    """The staff steps of the notes of each grace carrier, in the order of the group."""
    assert group is not None
    out: list[list[int]] = []
    for item in group.grace_items:
        carrier = item.carrier
        assert isinstance(carrier, NoteCarrier)
        out.append([grace.staff_step for grace in carrier.notes])

    return out


def test_a_grace_carrier_can_stand_in_the_middle_of_its_group() -> None:
    document = score()
    host, leaf = _host(document)
    first = _add(document=document, host=host, step=0)
    _add(document=document, host=host, step=1, value=RhythmicValue.THIRTY_SECOND, after=first)

    _add(document=document, host=host, step=2, value=RhythmicValue.EIGHTH, after=first)

    assert _steps(group=leaf.grace_before) == [[0], [2], [1]]
    assert taken_from(leaf=leaf) == Fraction(1, 16) + Fraction(1, 8) + Fraction(1, 32)


def test_without_a_place_a_grace_carrier_stands_first_and_goes_with_an_undo() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, step=0)
    group = leaf.grace_before

    _run(
        document=document,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=GracePlacement.BEFORE,
            grace_type=GraceType.APPOGGIATURA,
            written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
            staff_id=document.staffs[0].id,
            staff_step=1,
            accidental=Accidental.NATURAL,
        ),
    ).rollback()
    assert _steps(group=leaf.grace_before) == [[0]]
    assert leaf.grace_before is group

    log = _run(
        document=document,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=GracePlacement.BEFORE,
            grace_type=GraceType.APPOGGIATURA,
            written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
            staff_id=document.staffs[0].id,
            staff_step=1,
            accidental=Accidental.NATURAL,
        ),
    )
    assert _steps(group=leaf.grace_before) == [[1], [0]]
    log.rollback()
    assert _steps(group=leaf.grace_before) == [[0]]


def test_the_place_must_be_a_grace_carrier_of_the_same_note_and_side() -> None:
    document = score()
    host, leaf = _host(document)
    after_the_note = _add(document=document, host=host, step=0, placement=GracePlacement.AFTER)
    other_host: Note = note(document, Fraction(1, 2))
    foreign = _add(document=document, host=other_host, step=0)

    for named in (host.note_carrier, after_the_note, foreign):
        with pytest.raises(MutationRejectedError, match="not a grace carrier of this note"):
            _run(
                document=document,
                intent=AddGraceNoteIntent(
                    host_carrier_id=host.note_carrier.id,
                    placement=GracePlacement.BEFORE,
                    grace_type=GraceType.APPOGGIATURA,
                    written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
                    staff_id=document.staffs[0].id,
                    staff_step=3,
                    accidental=Accidental.NATURAL,
                    after_carrier_id=named.id,
                ),
            )

    assert leaf.grace_before is None


def test_the_time_rule_still_holds_for_a_carrier_put_in_the_middle() -> None:
    document = score()
    host, leaf = _host(document)
    first = _add(document=document, host=host, step=0, value=RhythmicValue.EIGHTH)
    _add(document=document, host=host, step=1, value=RhythmicValue.SIXTEENTH, after=first)

    with pytest.raises(MutationRejectedError, match="all the time"):
        _add(document=document, host=host, step=2, value=RhythmicValue.EIGHTH, after=first)

    assert _steps(group=leaf.grace_before) == [[0], [1]]


def _join(
    *, document: ScoreDocument, carrier: NoteCarrier, step: int, accidental: Accidental | None
) -> MutationLog:
    return _run(
        document=document,
        intent=AddGraceCarrierNoteIntent(
            carrier_id=carrier.id,
            staff_id=document.staffs[0].id,
            staff_step=step,
            accidental=accidental,
        ),
    )


def test_a_note_joins_a_grace_carrier_without_changing_its_place_or_time() -> None:
    document = score()
    host, leaf = _host(document)
    carrier = _add(document=document, host=host, step=0)
    _add(document=document, host=host, step=5, after=carrier)
    taken = taken_from(leaf=leaf)

    log = _join(document=document, carrier=carrier, step=2, accidental=None)

    assert _steps(group=leaf.grace_before) == [[0, 2], [5]]
    assert taken_from(leaf=leaf) == taken
    log.rollback()
    assert _steps(group=leaf.grace_before) == [[0], [5]]


def test_a_joining_note_without_a_sign_reads_the_cell_of_its_group() -> None:
    """Key sharp on the host's step, host natural: a grace note before the host does not see the
    host's sign, so the one in force for it is the key's."""
    document = score()
    key(document, Fraction(0), (Accidental.SHARP,) + (Accidental.NATURAL,) * 6)
    host, _leaf = _host(document)
    carrier = _add(document=document, host=host, step=0)

    _join(document=document, carrier=carrier, step=-2, accidental=None)

    joined = next(grace for grace in carrier.notes if grace.staff_step == -2)
    assert joined.accidental is Accidental.SHARP


def test_a_note_cannot_join_what_is_not_a_grace_carrier() -> None:
    document = score()
    host, _leaf = _host(document)

    with pytest.raises(MutationRejectedError, match="not a grace carrier"):
        _join(document=document, carrier=host.note_carrier, step=2, accidental=None)


def _change_value(
    *, document: ScoreDocument, carrier: NoteCarrier, value: RhythmicValue
) -> MutationLog:
    return _run(
        document=document,
        intent=ChangeGraceValueIntent(
            carrier_id=carrier.id, written_value=DottedRhythmicValue(value=value)
        ),
    )


def test_a_grace_carrier_is_written_as_another_value_and_the_time_follows() -> None:
    document = score()
    host, leaf = _host(document)
    carrier = _add(document=document, host=host, step=0, value=RhythmicValue.SIXTEENTH)
    assert taken_from(leaf=leaf) == Fraction(1, 16)

    log = _change_value(document=document, carrier=carrier, value=RhythmicValue.EIGHTH)
    assert taken_from(leaf=leaf) == Fraction(1, 8)

    log.rollback()
    assert taken_from(leaf=leaf) == Fraction(1, 16)


def test_a_slashed_grace_carrier_follows_its_group_scale() -> None:
    document = score()
    host, leaf = _host(document)
    _run(
        document=document,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=GracePlacement.BEFORE,
            grace_type=GraceType.ACCIACCATURA,
            written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
            staff_id=document.staffs[0].id,
            staff_step=0,
            accidental=Accidental.NATURAL,
        ),
    )
    assert leaf.grace_before is not None
    carrier = _carrier_on(group=leaf.grace_before, step=0)

    _change_value(document=document, carrier=carrier, value=RhythmicValue.QUARTER)

    # a slashed quarter sounds a quarter of a quarter
    assert taken_from(leaf=leaf) == Fraction(1, 16)


def test_a_value_that_would_take_all_the_time_of_the_note_is_refused() -> None:
    document = score()
    host, leaf = _host(document)
    first = _add(document=document, host=host, step=0, value=RhythmicValue.SIXTEENTH)
    _add(document=document, host=host, step=1, value=RhythmicValue.EIGHTH, after=first)

    with pytest.raises(MutationRejectedError, match="all the time"):
        _change_value(document=document, carrier=first, value=RhythmicValue.EIGHTH)

    assert taken_from(leaf=leaf) == Fraction(3, 16)


def test_the_value_of_a_carrier_that_is_not_a_grace_carrier_is_not_changed_here() -> None:
    document = score()
    host, _leaf = _host(document)

    with pytest.raises(MutationRejectedError, match="not a grace carrier"):
        _change_value(document=document, carrier=host.note_carrier, value=RhythmicValue.EIGHTH)


def _grace_note(*, document: ScoreDocument, step: int = 2) -> tuple[Note, NoteCarrier]:
    host, _leaf = _host(document)
    carrier = _add(document=document, host=host, step=step)
    return carrier.notes[0], carrier


def test_a_grace_note_moves_to_another_step_like_a_note() -> None:
    document = score()
    grace, _carrier = _grace_note(document=document)
    ordinary: Note = note(document, Fraction(1, 2), step=4)

    _run(document=document, intent=ChangePitchIntent(note_id=grace.id, staff_step=4))

    assert grace.staff_step == 4
    assert _sounds(document=document, target=grace) == _sounds(document=document, target=ordinary)


def test_a_grace_note_takes_another_accidental_like_a_note() -> None:
    document = score()
    grace, _carrier = _grace_note(document=document)
    before: int = _sounds(document=document, target=grace)

    _run(
        document=document,
        intent=SetAccidentalIntent(note_id=grace.id, accidental=Accidental.SHARP),
    )

    assert _sounds(document=document, target=grace) == before + 1


def test_a_grace_note_keeps_its_sound_on_another_staff() -> None:
    document = score()
    grace, _carrier = _grace_note(document=document)
    before: int = _sounds(document=document, target=grace)

    _run(
        document=document,
        intent=MoveNoteToStaffIntent(
            note_id=grace.id, staff_id=document.staffs[1].id, mode=PitchEditMode.PRESERVE_PITCH
        ),
    )

    assert grace.staff is document.staffs[1]
    assert _sounds(document=document, target=grace) == before


def test_grace_notes_shift_by_a_step_and_skip_a_unison_of_their_chord() -> None:
    document = score()
    grace, carrier = _grace_note(document=document, step=2)
    _join(document=document, carrier=carrier, step=3, accidental=Accidental.NATURAL)

    _run(document=document, intent=ShiftStaffStepsIntent(note_ids=(grace.id,), delta=1))

    # one step up would sound the other note of the chord, so it goes one further
    assert grace.staff_step == 4


def test_a_clef_set_keeping_the_pitch_keeps_what_a_grace_note_sounds_like() -> None:
    document = score()
    grace, _carrier = _grace_note(document=document, step=2)
    before: int = _sounds(document=document, target=grace)

    _run(
        document=document,
        intent=SetClefIntent(
            staff_id=document.staffs[0].id,
            measure_id=document.measures[0].id,
            position=MeasurePosition.of(numerator=0, denominator=1),
            clef=Clef.BASS,
            octave_transposition=0,
            mode=PitchEditMode.PRESERVE_PITCH,
        ),
    )

    assert grace.staff_step != 2
    assert _sounds(document=document, target=grace) == before


def test_a_grace_carrier_takes_articulations_an_ornament_and_a_fingering() -> None:
    document = score()
    grace, carrier = _grace_note(document=document)

    _run(
        document=document,
        intent=SetArticulationIntent(
            carrier_id=carrier.id, articulations=frozenset({Articulation.STACCATO})
        ),
    )
    _run(
        document=document, intent=SetOrnamentIntent(carrier_id=carrier.id, ornament=Ornament.TRILL)
    )
    _run(document=document, intent=SetFingeringIntent(note_id=grace.id, fingering=Fingering.THUMB))

    assert carrier.articulations == frozenset({Articulation.STACCATO})
    assert carrier.ornament is Ornament.TRILL
    assert grace.fingering is Fingering.THUMB
