from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    Note,
    NoteCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateBeamIntent,
    InsertMeasureIntent,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations import (
    CreateBeamAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationWorkItem
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateBeamAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CheckRelationRequest,
    CreateBeamRequest,
)

from ...scene import (
    Score,
    Snapshot,
    apply_intent,
    build_engine,
    build_score,
    build_two_voices,
    note,
    note_at,
    quarters,
    rest,
    snapshot,
    value,
)

# CreateBeam (plan-try-it): beams the selected carriers, given in time order. The compiler only
# addresses; the analyzer refuses by the rules the relation guard keeps a beam by
# (relation-guard) — consecutive members touch in one voice, none is a quarter or longer — so a
# beam the user asks for is refused where a side effect would have been repaired.

_E: Fraction = Fraction(1, 8)
_Q: Fraction = Fraction(1, 4)


def _carrier(leaf: LeafRhythmicContainer) -> Carrier:
    carrier: Carrier | None = leaf.carrier
    assert carrier is not None

    return carrier


def _eighths(*, score: Score, count: int) -> list[Carrier]:
    """Eighths from beat one on staff steps 1, 2, ..., then quarters from the next beat; the
    eighths' carriers in order."""
    carriers: list[Carrier] = [
        _carrier(
            note(
                score=score,
                parent=score.voice,
                at=index * _E,
                rhythmic_value=RhythmicValue.EIGHTH,
                step=index + 1,
            )
        )
        for index in range(count)
    ]
    quarters(score=score, measure=0, beats=range((count + 1) // 2, 4))

    return carriers


def _create_beam(*, score: Score, carriers: Sequence[Carrier]) -> list[MutationWorkItem]:
    return list(
        CreateBeamAnalyzer().analyze(
            request=CreateBeamRequest(carriers=tuple(carriers)),
            geometry=ScoreGeometry(document=score.document),
        )
    )


def _beam_intent(*, carriers: Sequence[Carrier]) -> CreateBeamIntent:
    return CreateBeamIntent(carrier_ids=tuple(carrier.id for carrier in carriers))


# --- the compiler -------------------------------------------------------------------------


@pytest.mark.unit
def test_the_compiler_addresses_the_carriers_in_the_order_given_each_once() -> None:
    score: Score = build_score(measure_count=1)
    first, second = _eighths(score=score, count=2)

    requests: Sequence[MutationRequest] = build_compiler().compile(
        document=score.document,
        intent=CreateBeamIntent(carrier_ids=(second.id, first.id, second.id)),
    )

    assert requests == [CreateBeamRequest(carriers=(second, first))]


@pytest.mark.unit
def test_the_compiler_refuses_an_unknown_id() -> None:
    score: Score = build_score(measure_count=1)
    first, _ = _eighths(score=score, count=2)

    with pytest.raises(MutationRejectedError, match="ghost"):
        build_compiler().compile(
            document=score.document,
            intent=CreateBeamIntent(carrier_ids=(first.id, "ghost")),
        )


@pytest.mark.unit
def test_the_compiler_refuses_an_id_that_is_not_a_carrier() -> None:
    score: Score = build_score(measure_count=1)
    first, second = _eighths(score=score, count=2)
    assert isinstance(second, NoteCarrier)

    with pytest.raises(MutationRejectedError, match="must be Carrier, got Note"):
        build_compiler().compile(
            document=score.document,
            intent=CreateBeamIntent(carrier_ids=(first.id, second.notes[0].id)),
        )


# --- the analyzer -------------------------------------------------------------------------


@pytest.mark.unit
def test_touching_short_carriers_are_beamed() -> None:
    """A dotted eighth and an eighth rest are short: dots are ignored, a rest is judged like a
    note."""
    score: Score = build_score(measure_count=1)
    dotted: Carrier = _carrier(
        note(
            score=score,
            parent=score.voice,
            at=Fraction(0),
            rhythmic_value=RhythmicValue.EIGHTH,
            dots=1,
            step=1,
        )
    )
    sixteenth: Carrier = _carrier(
        note(
            score=score,
            parent=score.voice,
            at=3 * Fraction(1, 16),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=2,
        )
    )
    eighth_rest: Carrier = _carrier(
        rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.EIGHTH)
    )
    eighth: Carrier = _carrier(
        note(
            score=score, parent=score.voice, at=3 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=3
        )
    )
    quarters(score=score, measure=0, beats=(2, 3))
    carriers: tuple[Carrier, ...] = (dotted, sixteenth, eighth_rest, eighth)

    assert _create_beam(score=score, carriers=carriers) == [CreateBeamAction(carriers=carriers)]


@pytest.mark.unit
@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_two_carriers_are_refused(count: int) -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[Carrier] = _eighths(score=score, count=2)

    with pytest.raises(MutationRejectedError, match="at least two"):
        _create_beam(score=score, carriers=carriers[:count])


@pytest.mark.unit
def test_a_carrier_already_in_another_beam_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[Carrier] = _eighths(score=score, count=4)
    Beam.create(carriers=carriers[:2])

    with pytest.raises(MutationRejectedError, match="already part of another beam"):
        _create_beam(score=score, carriers=carriers[1:3])


@pytest.mark.unit
def test_a_grace_carrier_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[Carrier] = _eighths(score=score, count=2)
    first_leaf: CarrierOwner = carriers[0].owner
    assert isinstance(first_leaf, LeafRhythmicContainer)
    group: GraceGroup = GraceGroup.create(
        leaf=first_leaf,
        grace_type=GraceType.ACCIACCATURA,
        placement=GracePlacement.BEFORE,
    )
    grace: NoteCarrier = NoteCarrier.create(
        owner=GraceItem.create(grace_group=group, rhythmic_value=value(RhythmicValue.EIGHTH))
    )
    Note.create(note_carrier=grace, staff=score.staff, staff_step=0, accidental=Accidental.NATURAL)

    with pytest.raises(MutationRejectedError, match="grace notes"):
        _create_beam(score=score, carriers=[grace, *carriers])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dots", "is_rest"),
    [
        pytest.param(0, False, id="quarter"),
        pytest.param(1, False, id="dotted quarter"),
        pytest.param(0, True, id="quarter rest"),
    ],
)
def test_a_carrier_of_a_quarter_or_longer_is_refused(dots: int, is_rest: bool) -> None:
    score: Score = build_score(measure_count=1)
    eighth: Carrier = _carrier(
        note(
            score=score,
            parent=score.voice,
            at=Fraction(0),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=1,
        )
    )
    long_leaf: LeafRhythmicContainer = (
        rest(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.QUARTER)
        if is_rest
        else note(
            score=score,
            parent=score.voice,
            at=_E,
            rhythmic_value=RhythmicValue.QUARTER,
            dots=dots,
            step=2,
        )
    )

    with pytest.raises(MutationRejectedError, match="quarter or longer"):
        _create_beam(score=score, carriers=[eighth, _carrier(long_leaf)])


@pytest.mark.unit
def test_carriers_with_time_between_them_are_refused() -> None:
    """An eighth rest outside the selection lies between the second and the third."""
    score: Score = build_score(measure_count=1)
    carriers: list[Carrier] = _eighths(score=score, count=4)

    with pytest.raises(MutationRejectedError, match="must touch one after another"):
        _create_beam(score=score, carriers=[carriers[0], carriers[1], carriers[3]])


@pytest.mark.unit
def test_carriers_out_of_time_order_are_refused() -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[Carrier] = _eighths(score=score, count=2)

    with pytest.raises(MutationRejectedError, match="must touch one after another"):
        _create_beam(score=score, carriers=carriers[::-1])


@pytest.mark.unit
def test_carriers_of_two_voices_are_refused() -> None:
    """Beat one of voice one and the eighth after it in voice two touch on the timeline, but
    not in one voice."""
    first, second = build_two_voices(measure_count=1)
    upper: Carrier = _carrier(
        note(
            score=first,
            parent=first.voice,
            at=Fraction(0),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=1,
        )
    )
    lower: Carrier = _carrier(
        note(score=second, parent=second.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    )

    with pytest.raises(MutationRejectedError, match="must touch one after another"):
        _create_beam(score=first, carriers=[upper, lower])


# --- through the engine -------------------------------------------------------------------


def _eighths_across_the_barline() -> tuple[Score, list[Carrier]]:
    """Quarters on beats one to three of measure one, eighths (steps 1, 2) on beat four,
    eighths (steps 3, 4) on beat one of measure two and quarters after; the four eighths'
    carriers in order."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    places: tuple[Fraction, ...] = (Fraction(3, 4), Fraction(7, 8), Fraction(1), Fraction(9, 8))
    carriers: list[Carrier] = [
        _carrier(
            note(
                score=score,
                parent=score.voice,
                at=at,
                rhythmic_value=RhythmicValue.EIGHTH,
                step=index + 1,
            )
        )
        for index, at in enumerate(places)
    ]
    quarters(score=score, measure=1, beats=(1, 2, 3))

    return score, carriers


@pytest.mark.unit
def test_a_beam_across_the_barline_is_created_and_kept() -> None:
    score, carriers = _eighths_across_the_barline()

    apply_intent(score=score, intent=_beam_intent(carriers=carriers))

    assert [list(beam.members) for beam in find_beams(carriers=carriers)] == [carriers]


@pytest.mark.unit
def test_a_measure_inserted_inside_a_created_beam_cuts_it_into_the_runs_on_either_side() -> None:
    """The beam keeps the two eighths before the new measure; the two after it get a beam of
    their own. That beam is the relation guard's later run, created through the same analyzer
    a user's beam is, so it keeps the creation rules too."""
    score, carriers = _eighths_across_the_barline()
    apply_intent(score=score, intent=_beam_intent(carriers=carriers))
    beam: Beam = find_beams(carriers=carriers)[0]

    apply_intent(score=score, intent=InsertMeasureIntent(before_measure_id=score.measures[1].id))

    assert list(beam.members) == carriers[:2]
    assert [list(found.members) for found in find_beams(carriers=carriers)] == [
        carriers[:2],
        carriers[2:],
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "breaker",
    [pytest.param(RhythmicValue.QUARTER, id="a quarter"), pytest.param(None, id="a gap")],
)
def test_the_later_run_the_beam_check_beams_anew_keeps_the_creation_rules(
    breaker: RhythmicValue | None,
) -> None:
    """Two eighths, then a quarter in the beam or a quarter rest outside it, then two eighths;
    the check's beam for the last two passes the creation analyzer."""
    score: Score = build_score(measure_count=1)
    places: tuple[Fraction, ...] = (Fraction(0), _E, Fraction(1, 2), 5 * _E)
    eighths: list[Carrier] = [
        _carrier(
            note(
                score=score,
                parent=score.voice,
                at=at,
                rhythmic_value=RhythmicValue.EIGHTH,
                step=index + 1,
            )
        )
        for index, at in enumerate(places)
    ]
    middle: LeafRhythmicContainer = (
        note(score=score, parent=score.voice, at=_Q, rhythmic_value=breaker, step=9)
        if breaker is not None
        else rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    )
    quarters(score=score, measure=0, beats=(3,))
    members: list[Carrier] = (
        [*eighths[:2], _carrier(middle), *eighths[2:]] if breaker is not None else eighths
    )
    beam: Beam = Beam.create(carriers=members)

    build_engine().process(document=score.document, requests=[CheckRelationRequest(relation=beam)])

    assert [list(found.members) for found in find_beams(carriers=eighths)] == [
        eighths[:2],
        eighths[2:],
    ]


@pytest.mark.unit
def test_a_refused_beam_leaves_the_score_as_it_was() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[Carrier] = [note_at(score=score, at=beat * _Q).note_carrier for beat in range(2)]
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="quarter or longer"):
        apply_intent(score=score, intent=_beam_intent(carriers=carriers))

    assert snapshot(score=score) == before
    assert find_beams(carriers=carriers) == []
