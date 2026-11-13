from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    Ornament,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    ChangeDurationIntent,
    EditIntent,
    SetArticulationIntent,
    SetOrnamentIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    Score,
    Snapshot,
    apply_intent,
    apply_intents,
    build_score,
    four_quarters,
    insert_note,
    note,
    note_at,
    quarters,
    rest,
    rest_at,
    snapshot,
    value,
)

# SetOrnament: an in-place update on a note carrier, like SetArticulation. The ornament belongs
# to the carrier as a whole, so it is the same field whether the carrier holds one note or
# several. The score's shape never changes.

_UNKNOWN_ID: str = "no-such-entity"


def set_ornament(*, carrier_id: str, ornament: Ornament) -> EditIntent:
    return SetOrnamentIntent(carrier_id=carrier_id, ornament=ornament)


@pytest.mark.unit
def test_setting_an_ornament_changes_only_that_carrier_in_place() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=set_ornament(carrier_id=target.id, ornament=Ornament.TRILL),
    )

    assert snapshot(score=score) == before
    assert note_at(score=score, at=Fraction(1, 2)).note_carrier is target
    assert [
        note_at(score=score, at=Fraction(beat, 4)).note_carrier.ornament for beat in range(4)
    ] == [Ornament.NONE, Ornament.NONE, Ornament.TRILL, Ornament.NONE]


@pytest.mark.unit
def test_a_second_ornament_replaces_the_first() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 4)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intents(
        score=score,
        intents=[
            set_ornament(carrier_id=target.id, ornament=Ornament.TRILL),
            set_ornament(carrier_id=target.id, ornament=Ornament.TURN),
        ],
    )

    assert snapshot(score=score) == before
    assert target.ornament is Ornament.TURN


@pytest.mark.unit
def test_an_ornament_on_a_carrier_with_two_notes_belongs_to_the_carrier() -> None:
    score: Score = four_quarters()
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    assert len(carrier.notes) == 2
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=set_ornament(carrier_id=carrier.id, ornament=Ornament.UPPER_MORDENT),
    )

    assert snapshot(score=score) == before
    assert carrier.ornament is Ornament.UPPER_MORDENT
    assert len(carrier.notes) == 2


@pytest.mark.unit
def test_an_ornament_set_to_none_clears_it() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier

    apply_intents(
        score=score,
        intents=[
            set_ornament(carrier_id=target.id, ornament=Ornament.LOWER_MORDENT),
            set_ornament(carrier_id=target.id, ornament=Ornament.NONE),
        ],
    )

    assert target.ornament is Ornament.NONE


@pytest.mark.unit
def test_an_ornament_and_an_articulation_do_not_replace_each_other() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier

    apply_intents(
        score=score,
        intents=[
            set_ornament(carrier_id=target.id, ornament=Ornament.INVERTED_TURN),
            SetArticulationIntent(
                carrier_id=target.id, articulations=frozenset({Articulation.ACCENT})
            ),
        ],
    )

    assert (target.ornament, target.articulations) == (
        Ornament.INVERTED_TURN,
        {Articulation.ACCENT},
    )


@pytest.mark.unit
def test_an_ornament_on_a_rest_carrier_is_refused_and_changes_nothing() -> None:
    """A rest carrier has no ornament; the id must name a note carrier."""
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="NoteCarrier"):
        apply_intent(
            score=score,
            intent=set_ornament(
                carrier_id=rest_at(score=score, at=Fraction(0)).rest_carrier.id,
                ornament=Ornament.TRILL,
            ),
        )

    assert snapshot(score=score) == before


@pytest.mark.unit
def test_an_unknown_carrier_id_is_refused_and_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="not resolve"):
        apply_intent(
            score=score,
            intent=set_ornament(carrier_id=_UNKNOWN_ID, ornament=Ornament.TRILL),
        )

    assert snapshot(score=score) == before


@pytest.mark.unit
def test_undoing_an_ornament_restores_the_old_one_and_redo_sets_it_again() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intent(score=score, intent=set_ornament(carrier_id=target.id, ornament=Ornament.TRILL))

    log: MutationLog = apply_intent(
        score=score,
        intent=set_ornament(carrier_id=target.id, ornament=Ornament.TURN),
    )
    log.rollback()
    assert target.ornament is Ornament.TRILL

    log.reapply()
    assert note_at(score=score, at=Fraction(1, 2)).note_carrier.ornament is Ornament.TURN


@pytest.mark.unit
def test_a_piece_added_when_a_duration_crosses_the_barline_keeps_the_ornament() -> None:
    """A quarter on beat three becomes a dotted half: the same carrier to the barline and a
    new one after it, both with the ornament, as with the articulation."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1)
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intents(
        score=score,
        intents=[
            set_ornament(carrier_id=target.id, ornament=Ornament.TRILL),
            SetArticulationIntent(
                carrier_id=target.id, articulations=frozenset({Articulation.ACCENT})
            ),
        ],
    )

    apply_intent(
        score=score,
        intent=ChangeDurationIntent(
            carrier_id=target.id,
            written_value=value(RhythmicValue.HALF, 1),
        ),
    )

    second: NoteCarrier = note_at(score=score, at=Fraction(1)).note_carrier
    assert second is not target
    assert (target.ornament, second.ornament) == (Ornament.TRILL, Ornament.TRILL)
    assert (target.articulations, second.articulations) == (
        {Articulation.ACCENT},
        {Articulation.ACCENT},
    )
