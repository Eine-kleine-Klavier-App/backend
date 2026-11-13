from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    Fingering,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation.compiler import (
    EditIntent,
    ToggleArticulationIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    NEW_STEP,
    Score,
    Snapshot,
    apply_intent,
    apply_intents,
    build_score,
    crossing_half,
    four_quarters,
    insert_note,
    note_at,
    pending,
    planned_intent,
    quarters,
    rest,
    rest_at,
    snapshot,
)

# SetFingering / SetArticulation (editing-intents-2026-10): in-place updates on the selected
# element — fingering on a note, articulation on a note carrier. Nothing special for tied
# notes: only the named element changes. The score's shape never changes.

_Q: Fraction = Fraction(1, 4)
_UNKNOWN_ID: str = "no-such-entity"

_PENDING = pending(stage=3)

# TODO(owner): fingering sent with a carrier or a chord id is not decided yet — no test.


def set_fingering(*, note_id: str, fingering: Fingering) -> EditIntent:
    """``SetFingeringIntent(note_id, fingering)``."""
    return planned_intent("SetFingeringIntent", note_id=note_id, fingering=fingering)


def set_articulation(*, carrier_id: str, articulations: frozenset[Articulation]) -> EditIntent:
    """``SetArticulationIntent(carrier_id, articulations)``."""
    return planned_intent(
        "SetArticulationIntent",
        carrier_id=carrier_id,
        articulations=articulations,
    )


@pytest.mark.unit
@_PENDING
def test_setting_a_fingering_changes_only_that_note_in_place() -> None:
    score: Score = four_quarters()
    target: Note = note_at(score=score, at=_Q)
    before: Snapshot = snapshot(score=score)

    apply_intent(score=score, intent=set_fingering(note_id=target.id, fingering=Fingering.THUMB))

    assert snapshot(score=score) == before
    assert note_at(score=score, at=_Q) is target
    assert target.fingering is Fingering.THUMB
    assert [note_at(score=score, at=Fraction(beat, 4)).fingering for beat in range(4)] == [
        Fingering.NONE,
        Fingering.THUMB,
        Fingering.NONE,
        Fingering.NONE,
    ]


@pytest.mark.unit
@_PENDING
def test_a_second_fingering_replaces_the_first() -> None:
    score: Score = four_quarters()
    target: Note = note_at(score=score, at=_Q)
    before: Snapshot = snapshot(score=score)

    apply_intents(
        score=score,
        intents=[
            set_fingering(note_id=target.id, fingering=Fingering.THUMB),
            set_fingering(note_id=target.id, fingering=Fingering.RING),
        ],
    )

    assert snapshot(score=score) == before
    assert target.fingering is Fingering.RING


@pytest.mark.unit
@_PENDING
def test_a_fingering_on_one_note_of_a_chord_leaves_the_other_note() -> None:
    score: Score = four_quarters()
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    chord: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    lower, upper = chord.notes
    assert upper.staff_step == NEW_STEP
    before: Snapshot = snapshot(score=score)

    apply_intent(score=score, intent=set_fingering(note_id=upper.id, fingering=Fingering.LITTLE))

    assert snapshot(score=score) == before
    assert list(chord.notes) == [lower, upper]
    assert (lower.fingering, upper.fingering) == (Fingering.NONE, Fingering.LITTLE)


@pytest.mark.unit
@_PENDING
def test_a_fingering_on_a_tied_piece_changes_only_that_piece() -> None:
    score: Score = crossing_half()
    first: Note = note_at(score=score, at=Fraction(3, 4))
    second: Note = note_at(score=score, at=Fraction(1))
    before: Snapshot = snapshot(score=score)

    apply_intent(score=score, intent=set_fingering(note_id=first.id, fingering=Fingering.INDEX))

    assert snapshot(score=score) == before
    assert (first.fingering, second.fingering) == (Fingering.INDEX, Fingering.NONE)


@pytest.mark.unit
@_PENDING
def test_setting_an_articulation_changes_only_that_carrier_in_place() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=target.id, articulations=frozenset({Articulation.STACCATO})
        ),
    )

    assert snapshot(score=score) == before
    assert note_at(score=score, at=Fraction(1, 2)).note_carrier is target
    assert [
        note_at(score=score, at=Fraction(beat, 4)).note_carrier.articulations for beat in range(4)
    ] == [frozenset(), frozenset(), frozenset({Articulation.STACCATO}), frozenset()]


@pytest.mark.unit
@_PENDING
def test_a_second_articulation_replaces_the_first() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intents(
        score=score,
        intents=[
            set_articulation(
                carrier_id=target.id, articulations=frozenset({Articulation.STACCATO})
            ),
            set_articulation(carrier_id=target.id, articulations=frozenset({Articulation.ACCENT})),
        ],
    )

    assert snapshot(score=score) == before
    assert target.articulations == {Articulation.ACCENT}


@pytest.mark.unit
@_PENDING
def test_an_articulation_on_a_tied_piece_changes_only_that_piece() -> None:
    score: Score = crossing_half()
    first: NoteCarrier = note_at(score=score, at=Fraction(3, 4)).note_carrier
    second: NoteCarrier = note_at(score=score, at=Fraction(1)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=second.id, articulations=frozenset({Articulation.TENUTO})
        ),
    )

    assert snapshot(score=score) == before
    assert (first.articulations, second.articulations) == (
        frozenset(),
        frozenset({Articulation.TENUTO}),
    )


@pytest.mark.unit
@_PENDING
def test_a_fingering_for_an_unknown_id_is_refused_and_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="Could not resolve"):
        apply_intent(
            score=score,
            intent=set_fingering(note_id=_UNKNOWN_ID, fingering=Fingering.THUMB),
        )

    assert snapshot(score=score) == before
    assert all(
        note_at(score=score, at=Fraction(beat, 4)).fingering is Fingering.NONE for beat in range(4)
    )


@pytest.mark.unit
@_PENDING
def test_an_articulation_for_an_unknown_id_is_refused_and_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="Could not resolve"):
        apply_intent(
            score=score,
            intent=set_articulation(
                carrier_id=_UNKNOWN_ID, articulations=frozenset({Articulation.ACCENT})
            ),
        )

    assert snapshot(score=score) == before
    assert all(
        not note_at(score=score, at=Fraction(beat, 4)).note_carrier.articulations
        for beat in range(4)
    )


@pytest.mark.unit
@_PENDING
def test_an_empty_set_of_articulations_clears_them() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intents(
        score=score,
        intents=[
            set_articulation(carrier_id=target.id, articulations=frozenset({Articulation.FERMATA})),
            set_articulation(carrier_id=target.id, articulations=frozenset()),
        ],
    )

    assert snapshot(score=score) == before
    assert not target.articulations


@pytest.mark.unit
@_PENDING
def test_an_articulation_on_a_rest_carrier_is_refused_and_changes_nothing() -> None:
    """A rest carrier has no articulation; the id must name a note carrier."""
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="NoteCarrier"):
        apply_intent(
            score=score,
            intent=set_articulation(
                carrier_id=rest_at(score=score, at=Fraction(0)).rest_carrier.id,
                articulations=frozenset({Articulation.ACCENT}),
            ),
        )

    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_a_fingering_set_to_none_clears_it() -> None:
    score: Score = four_quarters()
    target: Note = note_at(score=score, at=_Q)
    before: Snapshot = snapshot(score=score)

    apply_intents(
        score=score,
        intents=[
            set_fingering(note_id=target.id, fingering=Fingering.MIDDLE),
            set_fingering(note_id=target.id, fingering=Fingering.NONE),
        ],
    )

    assert snapshot(score=score) == before
    assert target.fingering is Fingering.NONE


@pytest.mark.unit
@_PENDING
def test_a_fingering_on_a_note_carrier_is_refused_and_changes_nothing() -> None:
    """The id must name a note; a carrier id is not read as its notes."""
    score: Score = four_quarters()
    carrier: NoteCarrier = note_at(score=score, at=_Q).note_carrier
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="must be Note, got NoteCarrier"):
        apply_intent(
            score=score,
            intent=set_fingering(note_id=carrier.id, fingering=Fingering.THUMB),
        )

    assert snapshot(score=score) == before
    assert all(note.fingering is Fingering.NONE for note in carrier.notes)


@pytest.mark.unit
@_PENDING
def test_a_fingering_on_a_rest_carrier_is_refused_and_changes_nothing() -> None:
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="must be Note, got RestCarrier"):
        apply_intent(
            score=score,
            intent=set_fingering(
                note_id=rest_at(score=score, at=Fraction(0)).rest_carrier.id,
                fingering=Fingering.THUMB,
            ),
        )

    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_undoing_a_fingering_restores_the_old_one_and_redo_sets_it_again() -> None:
    score: Score = four_quarters()
    target: Note = note_at(score=score, at=_Q)
    apply_intent(score=score, intent=set_fingering(note_id=target.id, fingering=Fingering.THUMB))

    log: MutationLog = apply_intent(
        score=score,
        intent=set_fingering(note_id=target.id, fingering=Fingering.RING),
    )
    log.rollback()
    assert target.fingering is Fingering.THUMB

    log.reapply()
    assert note_at(score=score, at=_Q).fingering is Fingering.RING


@pytest.mark.unit
@_PENDING
def test_undoing_an_articulation_restores_the_old_one_and_redo_sets_it_again() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=target.id, articulations=frozenset({Articulation.STACCATO})
        ),
    )

    log: MutationLog = apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=target.id, articulations=frozenset({Articulation.ACCENT})
        ),
    )
    log.rollback()
    assert target.articulations == {Articulation.STACCATO}

    log.reapply()
    assert note_at(score=score, at=Fraction(1, 2)).note_carrier.articulations == {
        Articulation.ACCENT
    }


def toggle_articulation(*, carrier_id: str, articulation: Articulation) -> EditIntent:
    return ToggleArticulationIntent(carrier_id=carrier_id, articulation=articulation)


@pytest.mark.unit
def test_marks_that_combine_are_kept_together() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=target.id,
            articulations=frozenset({Articulation.FERMATA, Articulation.ACCENT}),
        ),
    )

    assert snapshot(score=score) == before
    assert target.articulations == {Articulation.FERMATA, Articulation.ACCENT}


@pytest.mark.unit
def test_two_marks_of_one_category_are_refused_and_change_nothing() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intent(
        score=score,
        intent=set_articulation(
            carrier_id=target.id, articulations=frozenset({Articulation.ACCENT})
        ),
    )
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="both marks of loudness"):
        apply_intent(
            score=score,
            intent=set_articulation(
                carrier_id=target.id,
                articulations=frozenset({Articulation.ACCENT, Articulation.MARCATO}),
            ),
        )

    assert snapshot(score=score) == before
    assert target.articulations == {Articulation.ACCENT}


@pytest.mark.unit
def test_two_marks_of_length_are_refused() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier

    with pytest.raises(MutationRejectedError, match="both marks of length"):
        apply_intent(
            score=score,
            intent=set_articulation(
                carrier_id=target.id,
                articulations=frozenset({Articulation.STACCATO, Articulation.TENUTO}),
            ),
        )

    assert not target.articulations


@pytest.mark.unit
def test_toggling_a_mark_puts_it_on_and_takes_it_off() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.STACCATO),
    )
    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.ACCENT),
    )
    assert target.articulations == {Articulation.STACCATO, Articulation.ACCENT}

    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.STACCATO),
    )

    assert snapshot(score=score) == before
    assert target.articulations == {Articulation.ACCENT}


@pytest.mark.unit
def test_toggling_a_mark_on_replaces_the_mark_of_its_category() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intents(
        score=score,
        intents=[
            toggle_articulation(carrier_id=target.id, articulation=Articulation.ACCENT),
            toggle_articulation(carrier_id=target.id, articulation=Articulation.STACCATO),
        ],
    )

    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.MARCATO),
    )

    assert target.articulations == {Articulation.MARCATO, Articulation.STACCATO}

    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.FERMATA),
    )

    assert target.articulations == {Articulation.MARCATO, Articulation.FERMATA}


@pytest.mark.unit
def test_undoing_a_toggle_restores_the_marks_and_redo_sets_them_again() -> None:
    score: Score = four_quarters()
    target: NoteCarrier = note_at(score=score, at=Fraction(1, 2)).note_carrier
    apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.ACCENT),
    )

    log: MutationLog = apply_intent(
        score=score,
        intent=toggle_articulation(carrier_id=target.id, articulation=Articulation.MARCATO),
    )
    assert target.articulations == {Articulation.MARCATO}

    log.rollback()
    assert target.articulations == {Articulation.ACCENT}

    log.reapply()
    assert target.articulations == {Articulation.MARCATO}


@pytest.mark.unit
def test_toggling_a_mark_on_a_rest_carrier_is_refused_and_changes_nothing() -> None:
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="NoteCarrier"):
        apply_intent(
            score=score,
            intent=toggle_articulation(
                carrier_id=rest_at(score=score, at=Fraction(0)).rest_carrier.id,
                articulation=Articulation.ACCENT,
            ),
        )

    assert snapshot(score=score) == before
