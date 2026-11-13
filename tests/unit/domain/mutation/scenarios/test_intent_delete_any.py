from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    KeySignatureChange,
    Slur,
)
from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    Note,
    NoteCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    GlissandoType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler import TieNotesIntent
from piano_app.domain.score.document.services.mutation.engine.analyzers.intent import (
    RemoveAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
)

from ...scene import (
    COMPLETED_STAGE,
    IntentNotImplementedError,
    Score,
    Snapshot,
    anchor_at,
    anchor_layout,
    apply_intent,
    build_engine,
    build_score,
    context_layout,
    crossing_half,
    delete_entities,
    eighth_triplet,
    find_tie,
    four_quarters,
    group_layout,
    layout,
    note,
    note_at,
    numbered_quarters,
    orphan_anchors,
    own_contexts,
    pending,
    quarters,
    refresh_score,
    signatures,
    slot,
    snapshot,
    tie_layout,
)

# DeleteBatch accepts any entity id of the score (editing-intents-2026-10): relations (a tie
# is removed this way), contexts, leaves and measures beside notes, carriers, rests and
# tuplets. Until a stage lands, the compiler's refusal of an id kind it does not support yet
# is the only failure these tests expect.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline
# the refusal message for the last measure is not decided; it is only expected to name it
_LAST_MEASURE: str = r"(?i)measure"

_RELATIONS_AND_CONTEXTS: int = 2
_MEASURES: int = 5


def delete_any(*, score: Score, entity_ids: Sequence[str], stage: int) -> MutationLog:
    """Run ``DeleteBatchIntent(entity_ids)``; a kind refused before ``stage`` lands is pending.

    Every other refusal, and any refusal once the stage is completed, stays a failure.
    """
    try:
        return delete_entities(score=score, entity_ids=entity_ids)
    except MutationRejectedError as error:
        if stage > COMPLETED_STAGE and "Unsupported delete targets" in str(error):
            raise IntentNotImplementedError(str(error)) from error

        raise


def _with_key_signature(*, score: Score, at: Fraction) -> KeySignatureChange:
    return KeySignatureChange.create(
        start=anchor_at(score=score, at=at),
        staff=score.staff,
        alterations=(Accidental.SHARP,) * 7,
    )


def _with_clef(*, score: Score, at: Fraction) -> None:
    build_engine().process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measures[int(at)],
                position=MeasurePosition.of_fraction(fraction=at - int(at)),
                staff=score.staff,
                clef=Clef.BASS,
            )
        ],
    )


def _numbered_measures(*, measure_count: int) -> Score:
    """Build measures of quarters numbered from staff step 1 across the whole score."""
    score: Score = build_score(measure_count=measure_count)
    for measure in range(measure_count):
        numbered_quarters(score=score, measure=measure, first_step=1 + 4 * measure)

    return score


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_tie_id_removes_only_the_tie() -> None:
    """Both pieces of the tied half stay, the very same notes, untied."""
    score: Score = crossing_half()
    first: Note = note_at(score=score, at=Fraction(3, 4))
    second: Note = note_at(score=score, at=Fraction(1))
    leaves, groups, _, anchors = snapshot(score=score)

    delete_any(
        score=score,
        entity_ids=[find_tie(note_with_tie=first).id],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert snapshot(score=score) == (leaves, groups, [], anchors)
    assert note_at(score=score, at=Fraction(3, 4)) is first
    assert note_at(score=score, at=Fraction(1)) is second
    assert list(first.relations) == []
    assert list(second.relations) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_beam_id_removes_only_the_beam() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.EIGHTH,
        step=1,
    )
    note(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    carriers: list[Carrier] = [
        note_at(score=score, at=Fraction(0)).note_carrier,
        note_at(score=score, at=_E).note_carrier,
    ]
    beam: Beam = Beam.create(carriers=carriers)
    before: Snapshot = snapshot(score=score)

    delete_any(score=score, entity_ids=[beam.id], stage=_RELATIONS_AND_CONTEXTS)

    assert snapshot(score=score) == before
    assert all(list(carrier.carrier_group_relations) == [] for carrier in carriers)
    assert note_at(score=score, at=Fraction(0)).note_carrier is carriers[0]
    assert note_at(score=score, at=_E).note_carrier is carriers[1]


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_glissando_id_removes_only_the_glissando() -> None:
    score: Score = build_score(measure_count=1)
    numbered_quarters(score=score, measure=0, first_step=1)
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    glissando: Glissando = Glissando.create(
        start_note=start,
        end_note=end,
        glissando_type=GlissandoType.STRAIGHT,
    )
    before: Snapshot = snapshot(score=score)

    delete_any(score=score, entity_ids=[glissando.id], stage=_RELATIONS_AND_CONTEXTS)

    assert snapshot(score=score) == before
    assert (list(start.relations), list(end.relations)) == ([], [])
    assert note_at(score=score, at=Fraction(0)) is start
    assert note_at(score=score, at=_Q) is end


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_clef_id_is_refused_for_the_clef_has_a_command_of_its_own() -> None:
    """A delete batch is for notes, tuplets, graces and relations: a clef asks how its notes
    are treated, which the batch cannot."""
    score: Score = four_quarters()
    _with_clef(score=score, at=_E)
    clef: Context = next(
        context
        for context in score.staff.contexts
        if isinstance(context, ClefChange) and context.clef is Clef.BASS
    )
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="its own command"):
        delete_entities(score=score, entity_ids=[clef.id])

    assert snapshot(score=score) == before
    assert clef in score.staff.contexts


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_key_signature_id_removes_the_key_signature_only() -> None:
    score: Score = four_quarters()
    key_signature: KeySignatureChange = _with_key_signature(score=score, at=_Q)
    before: Snapshot = snapshot(score=score)

    delete_any(score=score, entity_ids=[key_signature.id], stage=_RELATIONS_AND_CONTEXTS)

    assert snapshot(score=score) == before
    assert context_layout(score=score) == []
    assert own_contexts(score, score.staff.contexts) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_slur_id_removes_the_slur_and_keeps_the_notes_it_spanned() -> None:
    score: Score = four_quarters()
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(3, 4)),
        voices=[score.voice],
    )
    before: Snapshot = snapshot(score=score)
    assert context_layout(score=score) == [("Slur", (0, Fraction(0)), (0, Fraction(3, 4)))]

    delete_any(score=score, entity_ids=[slur.id], stage=_RELATIONS_AND_CONTEXTS)

    assert snapshot(score=score) == before
    assert context_layout(score=score) == []
    assert own_contexts(score, score.voice.contexts) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_tuplet_listed_with_the_tie_of_its_last_note_removes_both_once() -> None:
    """The triplet's last eighth (step 3) is tied to the quarter after it on the same step.

    The tie would go with the triplet anyway; naming it too changes nothing in the result.
    """
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=3)
    quarters(score=score, measure=0, beats=(3,))
    last: Note = note_at(score=score, at=_Q + 2 * _THIRD)
    outside: Note = note_at(score=score, at=_H)
    apply_intent(
        score=score,
        intent=TieNotesIntent(start_note_id=last.id, end_note_id=outside.id),
    )

    delete_any(
        score=score,
        entity_ids=[triplet.id, find_tie(note_with_tie=last).id],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "3"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert list(outside.relations) == []
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_mixed_batch_removes_a_note_a_tie_and_a_key_signature_in_one_gesture() -> None:
    """A note, a tie and a key signature go in one gesture.

    The quarter's hole is filled, both pieces of the tied half stay, and the key signature
    goes with the anchor only it held.
    """
    score: Score = crossing_half()
    key_signature: KeySignatureChange = _with_key_signature(score=score, at=_E)
    first_piece: Note = note_at(score=score, at=Fraction(3, 4))

    delete_any(
        score=score,
        entity_ids=[
            note_at(score=score, at=Fraction(0)).id,
            find_tie(note_with_tie=first_piece).id,
            key_signature.id,
        ],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "1"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert group_layout(score=score) == []
    assert context_layout(score=score) == []
    assert anchor_layout(score=score) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_leaf_its_carrier_and_its_tie_named_together_remove_the_piece_once() -> None:
    """Three ids of different kinds name the first piece of the tied half; it goes once.

    Its hole is filled and the second piece stays, untied.
    """
    score: Score = crossing_half()
    first_piece: Note = note_at(score=score, at=Fraction(3, 4))
    leaf: CarrierOwner = first_piece.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)

    delete_any(
        score=score,
        entity_ids=[
            leaf.id,
            first_piece.note_carrier.id,
            find_tie(note_with_tie=first_piece).id,
        ],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "rest"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


def _beamed_eighths() -> tuple[Score, list[NoteCarrier], Beam]:
    """Build four eighths (staff steps 1-4) and two quarters; the first three eighths are beamed."""
    score: Score = build_score(measure_count=1)
    for index in range(4):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(2, 3))
    carriers: list[NoteCarrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(3)
    ]

    return score, carriers, Beam.create(carriers=[*carriers])


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_beam_listed_with_its_first_carrier_is_removed_before_the_carrier() -> None:
    """Relations go first: the listed beam is removed while it is still the beam the intent
    named, then the carrier's cascade runs."""
    score, carriers, beam = _beamed_eighths()
    analysis: MutationAnalysis = RemoveAnalyzer().analyze(
        request=RemoveRequest(document=score.document, targets=(carriers[0], beam)),
        geometry=ScoreGeometry(document=score.document),
    )

    assert list(analysis) == [
        DeleteRequest(target=beam),
        DeleteRequest(target=carriers[0]),
    ]

    score, carriers, beam = _beamed_eighths()

    delete_any(
        score=score,
        entity_ids=[carriers[0].id, beam.id],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "rest"),
        *[slot(0, index * _E, _E, str(index + 1)) for index in range(1, 4)],
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert [list(carrier.carrier_group_relations) for carrier in carriers[1:]] == [[], []]
    assert orphan_anchors(score=score) == []


def _five_beamed_eighths() -> tuple[Score, list[NoteCarrier], Beam]:
    """Build six eighths (staff steps 1-6) and a quarter on beat four; the first five eighths
    are beamed."""
    score: Score = build_score(measure_count=1)
    for index in range(6):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(3,))
    carriers: list[NoteCarrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(5)
    ]

    return score, carriers, Beam.create(carriers=[*carriers])


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_beam_listed_with_an_inner_carrier_is_removed_whole_before_the_carrier() -> None:
    """The beam goes before its third carrier does, so the gap the carrier leaves cuts no
    runs out of it: 4-5 stay unbeamed like 1-2."""
    score, carriers, beam = _five_beamed_eighths()

    delete_any(
        score=score,
        entity_ids=[beam.id, carriers[2].id],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert [entry.content for entry in layout(score=score)] == [
        "1",
        "2",
        "rest",
        "4",
        "5",
        "6",
        "0",
    ]
    assert find_beams(carriers=[*carriers[:2], *carriers[3:]]) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_beam_listed_twice_is_removed_once() -> None:
    """The listed relations are reduced before the first yield, keeping their order."""
    score, carriers, beam = _five_beamed_eighths()
    request: RemoveRequest = RemoveRequest(document=score.document, targets=(beam, beam))

    assert list(
        RemoveAnalyzer().analyze(request=request, geometry=ScoreGeometry(document=score.document))
    ) == [DeleteRequest(target=beam)]

    build_engine().process(document=score.document, requests=[request])

    assert find_beams(carriers=carriers) == []


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_beam_listed_alone_leaves_its_members_untouched() -> None:
    score, carriers, beam = _five_beamed_eighths()
    before: Snapshot = snapshot(score=score)

    delete_any(score=score, entity_ids=[beam.id], stage=_RELATIONS_AND_CONTEXTS)

    assert snapshot(score=score) == before
    assert find_beams(carriers=carriers) == []
    assert [note_at(score=score, at=index * _E).note_carrier for index in range(5)] == carriers


@pytest.mark.unit
def test_deleting_a_middle_member_of_a_beam_cuts_it_at_the_gap() -> None:
    """The third note goes and a rest takes its room: the beam keeps 1-2 and 4-5 get a beam
    of their own."""
    score, carriers, beam = _five_beamed_eighths()

    delete_entities(score=score, entity_ids=[carriers[2].notes[0].id])

    assert [entry.content for entry in layout(score=score)] == [
        "1",
        "2",
        "rest",
        "4",
        "5",
        "6",
        "0",
    ]
    assert list(beam.members) == carriers[:2]
    assert [list(found.members) for found in find_beams(carriers=carriers[3:])] == [carriers[3:]]


@pytest.mark.unit
@pending(stage=_RELATIONS_AND_CONTEXTS)
def test_a_glissando_listed_with_its_end_note_is_removed_before_the_note() -> None:
    """Relations go first: the listed glissando is removed, then its end note."""
    score: Score = build_score(measure_count=1)
    numbered_quarters(score=score, measure=0, first_step=1)
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)
    glissando: Glissando = Glissando.create(
        start_note=start,
        end_note=end,
        glissando_type=GlissandoType.STRAIGHT,
    )

    delete_any(
        score=score,
        entity_ids=[end.id, glissando.id],
        stage=_RELATIONS_AND_CONTEXTS,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "1"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "3"),
        slot(0, Fraction(3, 4), _Q, "4"),
    ]
    assert list(start.relations) == []
    assert note_at(score=score, at=Fraction(0)) is start
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pending(stage=_MEASURES)
def test_a_measure_id_removes_the_measure_and_keeps_its_neighbours() -> None:
    """The middle measure goes with its elements; its neighbours keep content, measure and beat."""
    score: Score = _numbered_measures(measure_count=3)

    delete_any(score=score, entity_ids=[score.measures[1].id], stage=_MEASURES)

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert signatures(score=after) == [Fraction(1), Fraction(1)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        *[slot(1, Fraction(beat, 4), _Q, str(9 + beat)) for beat in range(4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@pending(stage=_MEASURES)
def test_two_adjacent_measure_ids_remove_both() -> None:
    score: Score = _numbered_measures(measure_count=4)

    delete_any(
        score=score,
        entity_ids=[score.measures[1].id, score.measures[2].id],
        stage=_MEASURES,
    )

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[3]]
    assert signatures(score=after) == [Fraction(1), Fraction(1)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        *[slot(1, Fraction(beat, 4), _Q, str(13 + beat)) for beat in range(4)],
    ]
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@pending(stage=_MEASURES)
def test_a_measure_and_a_note_inside_it_named_together_remove_the_measure_once() -> None:
    score: Score = _numbered_measures(measure_count=3)

    delete_any(
        score=score,
        entity_ids=[note_at(score=score, at=1 + _Q).id, score.measures[1].id],
        stage=_MEASURES,
    )

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        *[slot(1, Fraction(beat, 4), _Q, str(9 + beat)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@pending(stage=_MEASURES)
def test_the_last_measure_by_id_is_refused_and_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match=_LAST_MEASURE):
        delete_any(score=score, entity_ids=[score.measures[0].id], stage=_MEASURES)

    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before


@pytest.mark.unit
@pending(stage=_MEASURES)
def test_every_measure_by_id_is_refused_after_the_first_is_removed_and_changes_nothing() -> None:
    """The first measure goes, the second would be the last one left: the whole batch is undone."""
    score: Score = _numbered_measures(measure_count=2)
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match=_LAST_MEASURE):
        delete_any(
            score=score,
            entity_ids=[measure.id for measure in score.measures],
            stage=_MEASURES,
        )

    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before
