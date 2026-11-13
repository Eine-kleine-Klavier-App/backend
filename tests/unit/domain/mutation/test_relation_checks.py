from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GlissandoType,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando, Tie
from piano_app.domain.score.document.models.structural.rhythm import GraceGroup, GraceItem
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations import (
    CheckRelationAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.guards import RelationGuard
from piano_app.domain.score.document.services.mutation.engine.typing import MutationWorkItem
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CheckRelationRequest,
    CreateBeamRequest,
    UpdateBeamMembersRequest,
)

from ..scene import Score, build_score, build_two_voices, note, note_at, quarters, rest, value

# The relation checks (relation-guard), one invariant at a time. A check decides before its
# first yield and yields only requests, so its whole analysis is read at once.

_E: Fraction = Fraction(1, 8)
_Q: Fraction = Fraction(1, 4)
_EIGHTH: DottedRhythmicValue = value(RhythmicValue.EIGHTH)


def _line(*, score: Score, values: Sequence[DottedRhythmicValue]) -> None:
    """Notes of ``values`` side by side from beat one, on staff steps 1, 2, ..."""
    at: Fraction = Fraction(0)
    for index, written in enumerate(values):
        note(
            score=score,
            parent=score.voice,
            at=at,
            rhythmic_value=written.value,
            dots=written.dots_count,
            step=index + 1,
        )
        at += written.fraction


def _carriers(*, score: Score) -> list[Carrier]:
    """The carrier of every leaf of the voice, in order."""
    carriers: list[Carrier] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        assert carrier is not None
        carriers.append(carrier)

    return carriers


def _grace_note(*, score: Score) -> Note:
    """A grace note before the first leaf of the voice."""
    group: GraceGroup = GraceGroup.create(
        leaf=iter_leaves(score.voice)[0],
        grace_type=GraceType.ACCIACCATURA,
        placement=GracePlacement.BEFORE,
    )
    item: GraceItem = GraceItem.create(grace_group=group, rhythmic_value=_EIGHTH)

    return Note.create(
        note_carrier=NoteCarrier.create(owner=item),
        staff=score.staff,
        staff_step=0,
        accidental=Accidental.NATURAL,
    )


def _check_beam(*, score: Score, beam: Beam) -> list[MutationWorkItem]:
    return list(
        CheckRelationAnalyzer().analyze(
            request=CheckRelationRequest(relation=beam),
            geometry=ScoreGeometry(document=score.document),
        )
    )


def _check_tie(*, score: Score, tie: Tie) -> list[MutationWorkItem]:
    return list(
        CheckRelationAnalyzer().analyze(
            request=CheckRelationRequest(relation=tie),
            geometry=ScoreGeometry(document=score.document),
        )
    )


def _check_glissando(*, score: Score, glissando: Glissando) -> list[MutationWorkItem]:
    return list(
        CheckRelationAnalyzer().analyze(
            request=CheckRelationRequest(relation=glissando),
            geometry=ScoreGeometry(document=score.document),
        )
    )


# --- beam -----------------------------------------------------------------------------------


@pytest.mark.unit
def test_a_beam_of_short_neighbours_is_left_alone() -> None:
    """A dotted eighth is short: dots are ignored."""
    score: Score = build_score(measure_count=1)
    _line(
        score=score,
        values=[_EIGHTH, value(RhythmicValue.EIGHTH, 1), value(RhythmicValue.SIXTEENTH), _EIGHTH],
    )

    assert _check_beam(score=score, beam=Beam.create(carriers=_carriers(score=score))) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "too_long",
    [
        pytest.param(value(RhythmicValue.QUARTER), id="quarter"),
        pytest.param(value(RhythmicValue.QUARTER, 1), id="dotted quarter"),
        pytest.param(value(RhythmicValue.HALF), id="half"),
    ],
)
def test_a_member_of_a_quarter_or_longer_cuts_the_beam_and_leaves_it(
    too_long: DottedRhythmicValue,
) -> None:
    """The beam keeps the run before it; the run after it gets a beam of its own."""
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH, _EIGHTH, too_long, _EIGHTH, _EIGHTH])
    carriers: list[Carrier] = _carriers(score=score)
    beam: Beam = Beam.create(carriers=carriers)

    assert _check_beam(score=score, beam=beam) == [
        UpdateBeamMembersRequest(target=beam, carriers=tuple(carriers[:2])),
        CreateBeamRequest(carriers=tuple(carriers[3:])),
    ]


@pytest.mark.unit
def test_a_rest_of_a_quarter_leaves_the_beam_like_a_note() -> None:
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH, _EIGHTH])
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    note(score=score, parent=score.voice, at=2 * _Q, rhythmic_value=RhythmicValue.EIGHTH, step=3)
    note(score=score, parent=score.voice, at=5 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=4)
    carriers: list[Carrier] = _carriers(score=score)
    beam: Beam = Beam.create(carriers=carriers)

    assert _check_beam(score=score, beam=beam) == [
        UpdateBeamMembersRequest(target=beam, carriers=tuple(carriers[:2])),
        CreateBeamRequest(carriers=tuple(carriers[3:])),
    ]


@pytest.mark.unit
def test_an_eighth_rest_stays_in_the_beam() -> None:
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH])
    rest(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH)
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.EIGHTH, step=2)

    assert _check_beam(score=score, beam=Beam.create(carriers=_carriers(score=score))) == []


@pytest.mark.unit
def test_members_that_are_not_neighbours_cut_the_beam_into_runs() -> None:
    """An eighth rest outside the beam lies between its second and third members."""
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH, _EIGHTH])
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.EIGHTH)
    note(score=score, parent=score.voice, at=3 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=3)
    note(score=score, parent=score.voice, at=_Q * 2, rhythmic_value=RhythmicValue.EIGHTH, step=4)
    carriers: list[Carrier] = _carriers(score=score)
    members: list[Carrier] = [*carriers[:2], *carriers[3:]]
    beam: Beam = Beam.create(carriers=members)

    assert _check_beam(score=score, beam=beam) == [
        UpdateBeamMembersRequest(target=beam, carriers=tuple(members[:2])),
        CreateBeamRequest(carriers=tuple(members[2:])),
    ]


@pytest.mark.unit
def test_a_beam_over_a_sleeping_measure_is_cut_there() -> None:
    """Measure two holds nothing: its empty time keeps the eighths on either side apart."""
    score: Score = build_score(measure_count=3)
    for at, step in ((Fraction(3, 4), 1), (Fraction(7, 8), 2), (Fraction(2), 3), (2 + _E, 4)):
        note(score=score, parent=score.voice, at=at, rhythmic_value=RhythmicValue.EIGHTH, step=step)
    carriers: list[Carrier] = _carriers(score=score)
    beam: Beam = Beam.create(carriers=carriers)

    assert _check_beam(score=score, beam=beam) == [
        UpdateBeamMembersRequest(target=beam, carriers=tuple(carriers[:2])),
        CreateBeamRequest(carriers=tuple(carriers[2:])),
    ]


@pytest.mark.unit
def test_the_beam_keeps_its_first_run_of_two_and_a_lone_member_is_unbeamed() -> None:
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH, value(RhythmicValue.QUARTER), _EIGHTH, _EIGHTH])
    carriers: list[Carrier] = _carriers(score=score)
    beam: Beam = Beam.create(carriers=carriers)

    assert _check_beam(score=score, beam=beam) == [
        UpdateBeamMembersRequest(target=beam, carriers=tuple(carriers[2:])),
    ]


@pytest.mark.unit
def test_a_beam_left_with_no_run_of_two_is_removed() -> None:
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH, value(RhythmicValue.QUARTER), _EIGHTH])
    beam: Beam = Beam.create(carriers=_carriers(score=score))

    assert _check_beam(score=score, beam=beam) == [DeleteRequest(target=beam)]


@pytest.mark.unit
def test_a_beam_with_a_grace_member_is_not_judged() -> None:
    """Beside the grace note stands a quarter, which a judged beam would lose."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    grace: Note = _grace_note(score=score)
    beam: Beam = Beam.create(carriers=[grace.note_carrier, *_carriers(score=score)])

    assert _check_beam(score=score, beam=beam) == []


# --- tie and glissando ----------------------------------------------------------------------


@pytest.mark.unit
def test_a_tie_between_touching_notes_is_left_alone() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    tie: Tie = Tie.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=_Q),
    )

    assert _check_tie(score=score, tie=tie) == []


@pytest.mark.unit
def test_a_tie_across_a_barline_between_touching_notes_is_left_alone() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1, beats=(0,))
    tie: Tie = Tie.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
    )

    assert _check_tie(score=score, tie=tie) == []


@pytest.mark.unit
def test_a_tie_between_notes_of_two_voices_is_removed() -> None:
    """Beat one of voice one and beat two of voice two touch on the timeline, but not in one
    voice."""
    first, second = build_two_voices(measure_count=1)
    quarters(score=first, measure=0, beats=(0,))
    quarters(score=second, measure=0, beats=(1,))
    tie: Tie = Tie.create(
        start_note=note_at(score=first, at=Fraction(0)),
        end_note=note_at(score=second, at=_Q),
    )

    assert _check_tie(score=first, tie=tie) == [DeleteRequest(target=tie)]


@pytest.mark.unit
def test_a_tie_over_a_rest_is_removed() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 2))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    tie: Tie = Tie.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=2 * _Q),
    )

    assert _check_tie(score=score, tie=tie) == [DeleteRequest(target=tie)]


@pytest.mark.unit
def test_a_tie_over_a_sleeping_measure_is_removed() -> None:
    """Measure two holds nothing: its empty time keeps the neighbouring leaves apart."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0)
    quarters(score=score, measure=2)
    tie: Tie = Tie.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(2)),
    )

    assert _check_tie(score=score, tie=tie) == [DeleteRequest(target=tie)]


@pytest.mark.unit
def test_a_tie_with_a_grace_note_is_not_judged() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(1,))
    grace: Note = _grace_note(score=score)
    tie: Tie = Tie.create(start_note=grace, end_note=note_at(score=score, at=_Q))

    assert _check_tie(score=score, tie=tie) == []


@pytest.mark.unit
def test_a_glissando_between_touching_notes_is_left_alone() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    glissando: Glissando = Glissando.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    assert _check_glissando(score=score, glissando=glissando) == []


@pytest.mark.unit
def test_a_glissando_over_a_rest_is_removed() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 2))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    glissando: Glissando = Glissando.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=2 * _Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    assert _check_glissando(score=score, glissando=glissando) == [DeleteRequest(target=glissando)]


@pytest.mark.unit
def test_a_glissando_with_a_grace_note_is_not_judged() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(1,))
    grace: Note = _grace_note(score=score)
    glissando: Glissando = Glissando.create(
        start_note=grace,
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    assert _check_glissando(score=score, glissando=glissando) == []


# --- the relation guard ---------------------------------------------------------------------


@pytest.mark.unit
def test_the_relation_guard_checks_every_relation_once_in_document_order() -> None:
    """Four beamed eighths: a tie from the second to the third and a glissando from the third to
    the fourth. Each relation is checked once, from the leaf it is first reached from."""
    score: Score = build_score(measure_count=1)
    _line(score=score, values=[_EIGHTH] * 4)
    carriers: list[Carrier] = _carriers(score=score)
    beam: Beam = Beam.create(carriers=carriers)
    tie: Tie = Tie.create(
        start_note=note_at(score=score, at=_E),
        end_note=note_at(score=score, at=2 * _E),
    )
    glissando: Glissando = Glissando.create(
        start_note=note_at(score=score, at=2 * _E),
        end_note=note_at(score=score, at=3 * _E),
        glissando_type=GlissandoType.STRAIGHT,
    )

    assert RelationGuard().search_fixes(
        document=score.document,
        geometry=ScoreGeometry(document=score.document),
    ) == [
        CheckRelationRequest(relation=beam),
        CheckRelationRequest(relation=tie),
        CheckRelationRequest(relation=glissando),
    ]
