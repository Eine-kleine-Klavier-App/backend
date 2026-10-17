from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.notation import (
    RhythmicValue,
    StemDirection,
    StemOverride,
)
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    EditIntent,
    ResetStemIntent,
    SetStemIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

from ..scene import Score, build_score, delete_entities, insert_note, quarters

# How the user wants a stem drawn: a field of the note carrier, changed by an ordinary
# update through the engine and gone together with the carrier. Nothing in the logic
# reads it.

_UP: StemOverride = StemOverride(direction=StemDirection.UP, length_percent=140)


def _carriers(*, score: Score) -> list[NoteCarrier]:
    carriers: list[NoteCarrier] = []
    for child in score.voice.children:
        if isinstance(child, LeafRhythmicContainer) and isinstance(child.carrier, NoteCarrier):
            carriers.append(child.carrier)

    return carriers


def _apply(*, score: Score, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


# --- the override value ------------------------------------------------------------------


@pytest.mark.unit
def test_a_stem_override_leaves_the_length_alone_by_default() -> None:
    assert StemOverride(direction=StemDirection.DOWN).length_percent == 100


@pytest.mark.unit
@pytest.mark.parametrize("length_percent", [0, -50])
def test_a_stem_length_must_be_a_positive_percentage(length_percent: int) -> None:
    with pytest.raises(ValueError, match="positive percentage"):
        StemOverride(direction=StemDirection.UP, length_percent=length_percent)


@pytest.mark.unit
def test_a_new_carrier_draws_its_stem_automatically() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)

    assert all(carrier.stem is None for carrier in _carriers(score=score))


# --- setting and resetting stems -------------------------------------------------------------


@pytest.mark.unit
def test_a_stem_override_is_saved_on_its_carrier() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    assert carrier.stem == _UP


@pytest.mark.unit
def test_a_selection_of_stems_is_set_in_one_gesture() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carriers: list[NoteCarrier] = _carriers(score=score)

    log: MutationLog = _apply(
        score=score,
        intent=SetStemIntent(carrier_ids=(carriers[0].id, carriers[2].id), override=_UP),
    )
    assert [carrier.stem for carrier in carriers] == [_UP, None, _UP, None]

    log.rollback()
    assert all(carrier.stem is None for carrier in carriers)


@pytest.mark.unit
def test_resetting_a_stem_draws_it_automatically_again() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]
    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    _apply(score=score, intent=ResetStemIntent(carrier_ids=(carrier.id,)))

    assert carrier.stem is None


@pytest.mark.unit
def test_a_stem_edit_naming_a_rest_is_refused() -> None:
    score: Score = build_score(bars=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    rest_leaf = score.voice.children[1]
    assert isinstance(rest_leaf, LeafRhythmicContainer)
    assert isinstance(rest_leaf.carrier, RestCarrier)

    with pytest.raises(MutationRejectedError, match="must be NoteCarrier"):
        _apply(score=score, intent=SetStemIntent(carrier_ids=(rest_leaf.carrier.id,), override=_UP))


@pytest.mark.unit
def test_a_stem_edit_naming_nothing_is_refused() -> None:
    score: Score = build_score(bars=1)

    with pytest.raises(MutationRejectedError, match="at least one note carrier"):
        _apply(score=score, intent=SetStemIntent(carrier_ids=(), override=_UP))


# --- the override follows its carrier ---------------------------------------------------------


@pytest.mark.unit
def test_undoing_a_carrier_delete_brings_its_stem_back() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[1]
    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    log: MutationLog = delete_entities(score=score, entity_ids=[carrier.id])
    assert carrier not in _carriers(score=score)

    log.rollback()
    assert carrier in _carriers(score=score)
    assert carrier.stem == _UP


@pytest.mark.unit
def test_a_note_joining_the_chord_keeps_the_carrier_and_its_stem() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]
    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)

    assert len(carrier.notes) == 2
    assert carrier.stem == _UP


@pytest.mark.unit
def test_a_carrier_replaced_by_a_new_one_loses_its_stem() -> None:
    """A half over the first beat recreates the slot: a new carrier, drawn automatically."""
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]
    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    assert carrier not in _carriers(score=score)
    assert _carriers(score=score)[0].stem is None


@pytest.mark.unit
def test_a_carrier_listed_twice_is_set_once() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]

    log: MutationLog = _apply(
        score=score,
        intent=SetStemIntent(carrier_ids=(carrier.id, carrier.id), override=_UP),
    )
    log.rollback()

    assert carrier.stem is None


@pytest.mark.unit
def test_undoing_a_reset_brings_the_override_back_and_redo_drops_it_again() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carrier: NoteCarrier = _carriers(score=score)[0]
    _apply(score=score, intent=SetStemIntent(carrier_ids=(carrier.id,), override=_UP))

    log: MutationLog = _apply(score=score, intent=ResetStemIntent(carrier_ids=(carrier.id,)))
    log.rollback()
    assert carrier.stem == _UP

    log.reapply()
    assert carrier.stem is None
