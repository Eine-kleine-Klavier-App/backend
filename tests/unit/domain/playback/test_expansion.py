from fractions import Fraction

import pytest

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    DottedRhythmicValue,
    GlissandoType,
    GracePlacement,
    GraceType,
    Ornament,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Glissando, Tie
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.playback import (
    ORNAMENT_UNIT,
    PlayedNote,
    build_rest_hosts,
    build_route,
    build_sounds,
    expand_sounds,
)

from ..pitch.test_accidental_inference import note as note_on_staff
from ..scene import Score, anchor_at, build_score, insert_note, note, note_at, quarters, rest

# A measure of the scene is four quarters, one whole note long; its notes sit on staff step 0
# (E4, MIDI 64) and the key is C major, so the note above is F (65) and the one below D (62).
# Times are in whole notes, in the time of the route.

_Q: Fraction = Fraction(1, 4)
_U: Fraction = ORNAMENT_UNIT

type Shape = tuple[int, Fraction, Fraction]


def _played(*, document: ScoreDocument) -> list[PlayedNote]:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    return expand_sounds(
        sounds=build_sounds(document=document, geometry=geometry, route=route),
        document=document,
        geometry=geometry,
        pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
    )


def _played_with_rests(*, document: ScoreDocument) -> list[PlayedNote]:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    return expand_sounds(
        sounds=build_sounds(document=document, geometry=geometry, route=route),
        document=document,
        geometry=geometry,
        pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
        rests=build_rest_hosts(document=document, geometry=geometry, route=route),
    )


def _shapes(*, notes: list[PlayedNote]) -> list[Shape]:
    return [(played.pitch, played.start, played.end) for played in notes]


@pytest.mark.unit
def test_a_plain_note_is_played_as_it_is() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(1,))

    assert _shapes(notes=_played(document=score.document)) == [(64, _Q, 2 * _Q)]


@pytest.mark.unit
def test_an_upper_mordent_is_the_note_the_one_above_and_the_note_again() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    note_at(score=score, at=Fraction(0)).note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)

    assert _shapes(notes=_played(document=score.document)) == [
        (64, Fraction(0), _U),
        (65, _U, 2 * _U),
        (64, 2 * _U, _Q),
    ]


@pytest.mark.unit
def test_a_trill_on_a_half_note_fills_it_with_short_notes() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=0,
    )
    note_at(score=score, at=Fraction(0)).note_carrier.set_ornament(ornament=Ornament.TRILL)

    shapes: list[Shape] = _shapes(notes=_played(document=score.document))

    assert [pitch for pitch, _, _ in shapes] == [64, 65] * 7 + [64]
    assert shapes[-1] == (64, 14 * _U, Fraction(1, 2))


@pytest.mark.unit
def test_a_tremolo_on_a_half_note_strikes_it_again_every_unit() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=0,
    )
    note_at(score=score, at=Fraction(0)).note_carrier.set_ornament(ornament=Ornament.TREMOLO_3)

    shapes: list[Shape] = _shapes(notes=_played(document=score.document))

    assert [pitch for pitch, _, _ in shapes] == [64] * 16
    assert shapes[0] == (64, Fraction(0), _U)
    assert shapes[-1] == (64, 15 * _U, Fraction(1, 2))


@pytest.mark.unit
def test_every_new_note_of_a_chord_is_expanded() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    carrier.set_ornament(ornament=Ornament.LOWER_MORDENT)

    played: list[PlayedNote] = _played(document=score.document)

    assert len(played) == 6
    assert {note.source for note in played} == set(carrier.notes)
    assert all(
        (first.start, first.end) == (Fraction(0), _U)
        for first in played
        if first.start == Fraction(0)
    )


@pytest.mark.unit
def test_a_tie_chain_is_expanded_once_by_the_carrier_where_it_began() -> None:
    """Two tied quarters: the turn of the first carrier is played over both, the trill of the
    second is not played."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    first: Note = note_at(score=score, at=Fraction(0))
    second: Note = note_at(score=score, at=_Q)
    Tie.create(start_note=first, end_note=second)
    first.note_carrier.set_ornament(ornament=Ornament.TURN)
    second.note_carrier.set_ornament(ornament=Ornament.TRILL)

    played: list[PlayedNote] = _played(document=score.document)

    assert [note.pitch for note in played] == [65, 64, 62, 64]
    assert played[-1].end == 2 * _Q


@pytest.mark.unit
def test_an_ornament_of_a_carrier_with_one_tied_note_acts_on_its_new_note_only() -> None:
    """Chords on beats one and two, the lower notes tied; the mordent is on the second chord."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    lower: Note = note_at(score=score, at=Fraction(0))
    Tie.create(start_note=lower, end_note=note_at(score=score, at=_Q))
    note_at(score=score, at=_Q).note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)

    played: list[PlayedNote] = _played(document=score.document)

    held: list[PlayedNote] = [note for note in played if note.source is lower]
    assert _shapes(notes=held) == [(64, Fraction(0), 2 * _Q)]
    mordent: list[PlayedNote] = [note for note in played if note.start >= _Q]
    assert len(mordent) == 3
    assert mordent[-1].end == 2 * _Q


@pytest.mark.unit
def test_a_repeated_ornament_is_expanded_in_each_pass() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0,))
    note_at(score=score, at=Fraction(0)).note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)
    Refrain.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(1)),
        times=2,
    )

    played: list[PlayedNote] = _played(document=score.document)

    assert [note.start for note in played] == [
        Fraction(0),
        _U,
        2 * _U,
        Fraction(1),
        1 + _U,
        1 + 2 * _U,
    ]


def _chord_of_two(*, value: RhythmicValue = RhythmicValue.QUARTER) -> tuple[Score, Note, Note]:
    """One chord on beat one of the first measure: staff step 0 (E4) and staff step 9 above it."""
    score: Score = build_score(measure_count=1)
    note(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=value, step=0)
    insert_note(score=score, at=Fraction(0), rhythmic_value=value)
    lower, upper = note_at(score=score, at=Fraction(0)).note_carrier.notes

    return score, lower, upper


@pytest.mark.unit
def test_an_arpeggio_up_starts_the_notes_from_the_bottom_and_holds_them() -> None:
    score, lower, upper = _chord_of_two()
    lower.note_carrier.set_articulations(articulations=frozenset({Articulation.ARPEGGIO_UP}))

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.source, note.start, note.end) for note in played] == [
        (lower, Fraction(0), _Q),
        (upper, _U, _Q),
    ]


@pytest.mark.unit
def test_an_arpeggio_down_starts_the_notes_from_the_top() -> None:
    score, lower, upper = _chord_of_two()
    lower.note_carrier.set_articulations(articulations=frozenset({Articulation.ARPEGGIO_DOWN}))

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.source, note.start) for note in played] == [(upper, Fraction(0)), (lower, _U)]


@pytest.mark.unit
def test_the_step_of_an_arpeggio_on_a_short_chord_is_shared_by_its_notes() -> None:
    """A 32nd note chord: the room is one unit, shared by the two notes."""
    score, lower, _ = _chord_of_two(value=RhythmicValue.THIRTY_SECOND)
    lower.note_carrier.set_articulations(articulations=frozenset({Articulation.ARPEGGIO_UP}))

    starts: list[Fraction] = [note.start for note in _played(document=score.document)]

    assert starts == [Fraction(0), _U / 2]


@pytest.mark.unit
def test_an_arpeggio_across_two_staves_goes_by_the_staff_first() -> None:
    """The hands are crossed: the note of the bass staff sounds higher (E4) than the note of
    the treble staff (C4). Up begins on the lower staff, whatever it sounds."""
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=2, measure_count=1
    )
    treble: Note = note_on_staff(document, Fraction(0), Accidental.NATURAL, step=-2, staff=0)
    bass: Note = Note.create(
        note_carrier=treble.note_carrier,
        staff=document.staffs[1],
        staff_step=12,
        accidental=Accidental.NATURAL,
    )
    treble.note_carrier.set_articulations(articulations=frozenset({Articulation.ARPEGGIO_UP}))

    played: list[PlayedNote] = _played(document=document)

    assert [(note.source, note.pitch) for note in played] == [(bass, 64), (treble, 60)]


@pytest.mark.unit
def test_an_arpeggio_shifts_the_start_of_each_ornament_with_it() -> None:
    score, lower, upper = _chord_of_two()
    lower.note_carrier.set_articulations(articulations=frozenset({Articulation.ARPEGGIO_UP}))
    lower.note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)

    played: list[PlayedNote] = _played(document=score.document)

    assert next(note.start for note in played if note.source is upper) == _U
    assert len([note for note in played if note.source is lower]) == 3
    assert len([note for note in played if note.source is upper]) == 3


@pytest.mark.unit
def test_a_glissando_divides_the_sound_of_its_start_note_among_its_steps() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=-2,
    )
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=5)
    Glissando.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    played: list[PlayedNote] = _played(document=score.document)

    assert [note.pitch for note in played] == [60, 62, 64, 65, 67, 69, 71, 72]
    # the note sounds as itself for half of its stretch, then the steps share the other half
    share: Fraction = _Q / 2 / 7
    assert (played[0].start, played[0].end) == (Fraction(0), _Q / 2 + share)
    assert [(note.start, note.end) for note in played[1:7]] == [
        (_Q / 2 + index * share, _Q / 2 + (index + 1) * share) for index in range(1, 7)
    ]
    assert (played[7].start, played[7].end) == (_Q, 2 * _Q)


@pytest.mark.unit
def test_a_glissando_from_a_tied_chain_slides_in_the_half_of_its_last_note() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=-2,
    )
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=-2)
    note(score=score, parent=score.voice, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, step=0)
    first, second = note_at(score=score, at=Fraction(0)), note_at(score=score, at=_Q)
    Tie.create(start_note=first, end_note=second)
    Glissando.create(
        start_note=second,
        end_note=note_at(score=score, at=2 * _Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    played: list[PlayedNote] = _played(document=score.document)

    # C4 held through the first quarter and the first half of the second, then C D, then the E
    assert [note.pitch for note in played] == [60, 62, 64]
    assert played[0].start == 0
    assert played[0].end == _Q + _Q / 2 + _Q / 2 / 2
    assert played[-1].start == 2 * _Q


@pytest.mark.unit
def test_a_glissando_takes_the_place_of_the_ornament_on_its_start_note() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=-2,
    )
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=0)
    start: Note = note_at(score=score, at=Fraction(0))
    start.note_carrier.set_ornament(ornament=Ornament.TRILL)
    Glissando.create(
        start_note=start,
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.WAVY,
    )

    played: list[PlayedNote] = _played(document=score.document)

    assert [note.pitch for note in played] == [60, 62, 64]


def _grace(
    *,
    score: Score,
    host: Note | LeafRhythmicContainer,
    placement: GracePlacement,
    grace_type: GraceType = GraceType.APPOGGIATURA,
    values: tuple[RhythmicValue, ...] = (RhythmicValue.SIXTEENTH,),
    steps: tuple[int, ...] = (-2,),
) -> list[Note]:
    """A group of grace notes on the leaf of ``host`` (or on ``host`` itself, a leaf), one item for
    each value, each with one note on the staff step that goes with it."""
    leaf = host if isinstance(host, LeafRhythmicContainer) else host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    group: GraceGroup = GraceGroup.create(leaf=leaf, grace_type=grace_type, placement=placement)
    notes: list[Note] = []
    for value, step in zip(values, steps, strict=True):
        item: GraceItem = GraceItem.create(
            grace_group=group, rhythmic_value=DottedRhythmicValue(value=value)
        )
        notes.append(
            Note.create(
                note_carrier=NoteCarrier.create(owner=item),
                staff=score.staff,
                staff_step=step,
                accidental=Accidental.NATURAL,
            )
        )

    return notes


def _one_quarter() -> tuple[Score, Note]:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))

    return score, note_at(score=score, at=Fraction(0))


_S: Fraction = Fraction(1, 16)


@pytest.mark.unit
def test_a_grace_note_before_a_note_sounds_first_and_the_note_starts_after_it() -> None:
    score, host = _one_quarter()
    (grace,) = _grace(score=score, host=host, placement=GracePlacement.BEFORE)

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.source, note.pitch, note.start, note.end) for note in played] == [
        (grace, 60, Fraction(0), _S),
        (host, 64, _S, _Q),
    ]


@pytest.mark.unit
def test_a_slashed_grace_note_sounds_a_quarter_of_what_is_written() -> None:
    score, host = _one_quarter()
    _grace(
        score=score,
        host=host,
        placement=GracePlacement.BEFORE,
        grace_type=GraceType.ACCIACCATURA,
    )

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.start, note.end) for note in played] == [
        (Fraction(0), _S / 4),
        (_S / 4, _Q),
    ]


@pytest.mark.unit
def test_a_grace_note_after_a_note_ends_where_the_note_ends_and_cuts_it_short() -> None:
    score, host = _one_quarter()
    (grace,) = _grace(score=score, host=host, placement=GracePlacement.AFTER)

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.source, note.start, note.end) for note in played] == [
        (host, Fraction(0), _Q - _S),
        (grace, _Q - _S, _Q),
    ]


@pytest.mark.unit
def test_the_grace_notes_of_a_group_follow_one_another() -> None:
    score, host = _one_quarter()
    first, second = _grace(
        score=score,
        host=host,
        placement=GracePlacement.BEFORE,
        values=(RhythmicValue.SIXTEENTH, RhythmicValue.THIRTY_SECOND),
        steps=(-2, -1),
    )

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.source, note.start, note.end) for note in played] == [
        (first, Fraction(0), _S),
        (second, _S, _S + _U),
        (host, _S + _U, _Q),
    ]


@pytest.mark.unit
def test_every_new_note_of_a_chord_starts_after_the_grace_notes() -> None:
    score, lower, upper = _chord_of_two()
    _grace(score=score, host=lower, placement=GracePlacement.BEFORE)

    played: list[PlayedNote] = _played(document=score.document)

    assert {(note.source, note.start) for note in played if note.source in (lower, upper)} == {
        (lower, _S),
        (upper, _S),
    }


@pytest.mark.unit
def test_the_grace_notes_of_a_tie_chain_take_from_its_two_ends() -> None:
    """Two tied quarters: a grace note before the first and one after the second."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    first: Note = note_at(score=score, at=Fraction(0))
    second: Note = note_at(score=score, at=_Q)
    Tie.create(start_note=first, end_note=second)
    _grace(score=score, host=first, placement=GracePlacement.BEFORE)
    _grace(score=score, host=second, placement=GracePlacement.AFTER)

    played: list[PlayedNote] = _played(document=score.document)

    held: list[PlayedNote] = [note for note in played if note.source is first]
    assert _shapes(notes=held) == [(64, _S, 2 * _Q - _S)]
    assert len(played) == 3


@pytest.mark.unit
def test_a_grace_note_on_a_leaf_in_the_middle_of_a_tie_sounds_over_the_held_note() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    first: Note = note_at(score=score, at=Fraction(0))
    middle: Note = note_at(score=score, at=_Q)
    Tie.create(start_note=first, end_note=middle)
    Tie.create(start_note=middle, end_note=note_at(score=score, at=2 * _Q))
    (grace,) = _grace(score=score, host=middle, placement=GracePlacement.BEFORE)

    played: list[PlayedNote] = _played(document=score.document)

    assert _shapes(notes=[note for note in played if note.source is first]) == [
        (64, Fraction(0), 3 * _Q)
    ]
    assert [(note.start, note.end) for note in played if note.source is grace] == [(_Q, _Q + _S)]


@pytest.mark.unit
def test_an_ornament_on_a_note_with_a_grace_note_starts_after_it() -> None:
    score, host = _one_quarter()
    _grace(score=score, host=host, placement=GracePlacement.BEFORE)
    host.note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)

    played: list[PlayedNote] = [
        note for note in _played(document=score.document) if note.source is host
    ]

    assert [note.start for note in played] == [_S, _S + _U, _S + 2 * _U]
    assert played[-1].end == _Q


def _articulated(*, mark: Articulation) -> tuple[Score, Note]:
    score, host = _one_quarter()
    host.note_carrier.set_articulations(articulations=frozenset({mark}))

    return score, host


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mark", "share"),
    [
        (Articulation.STACCATO, Fraction(1, 2)),
        (Articulation.STACCATISSIMO, Fraction(1, 4)),
        (Articulation.TENUTO, Fraction(1)),
        (Articulation.FERMATA, Fraction(1)),
        (Articulation.ACCENT, Fraction(1)),
    ],
)
def test_a_mark_of_length_shortens_the_sound_to_its_share(
    mark: Articulation, share: Fraction
) -> None:
    score, _ = _articulated(mark=mark)

    assert _shapes(notes=_played(document=score.document)) == [(64, Fraction(0), share * _Q)]


@pytest.mark.unit
def test_a_staccato_shortens_the_whole_tie_chain() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    first: Note = note_at(score=score, at=Fraction(0))
    Tie.create(start_note=first, end_note=note_at(score=score, at=_Q))
    first.note_carrier.set_articulations(articulations=frozenset({Articulation.STACCATO}))

    assert _shapes(notes=_played(document=score.document)) == [(64, Fraction(0), _Q)]


@pytest.mark.unit
def test_a_staccato_ornament_ends_at_the_shortened_end() -> None:
    score, host = _articulated(mark=Articulation.STACCATO)
    host.note_carrier.set_ornament(ornament=Ornament.UPPER_MORDENT)

    played: list[PlayedNote] = _played(document=score.document)

    assert [(note.start, note.end) for note in played] == [
        (Fraction(0), _U),
        (_U, 2 * _U),
        (2 * _U, _Q / 2),
    ]


@pytest.mark.unit
def test_every_note_of_an_arpeggio_is_held_to_the_shortened_end() -> None:
    score, lower, _ = _chord_of_two()
    lower.note_carrier.set_articulations(
        articulations=frozenset({Articulation.STACCATO, Articulation.ARPEGGIO_UP})
    )

    assert [note.end for note in _played(document=score.document)] == [_Q / 2, _Q / 2]


@pytest.mark.unit
def test_the_share_is_taken_of_what_a_grace_note_after_it_leaves() -> None:
    score, host = _articulated(mark=Articulation.STACCATO)
    _grace(score=score, host=host, placement=GracePlacement.AFTER)

    played: list[PlayedNote] = _played(document=score.document)

    assert (played[0].start, played[0].end) == (Fraction(0), (_Q - _S) / 2)


def _rest_then_a_quarter() -> tuple[Score, LeafRhythmicContainer, Note]:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = rest(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
    )
    quarters(score=score, measure=0, beats=(1,))

    return score, leaf, note_at(score=score, at=_Q)


@pytest.mark.unit
def test_a_grace_note_before_a_rest_sounds_from_where_the_rest_starts() -> None:
    score, host, quarter = _rest_then_a_quarter()
    (grace,) = _grace(score=score, host=host, placement=GracePlacement.BEFORE)

    played: list[PlayedNote] = _played_with_rests(document=score.document)

    assert [(note.source, note.pitch, note.start, note.end) for note in played] == [
        (grace, 60, Fraction(0), _S),
        (quarter, 64, _Q, 2 * _Q),
    ]


@pytest.mark.unit
def test_a_grace_note_after_a_rest_ends_where_the_rest_ends() -> None:
    score, host, _quarter = _rest_then_a_quarter()
    (grace,) = _grace(score=score, host=host, placement=GracePlacement.AFTER)

    played: list[PlayedNote] = _played_with_rests(document=score.document)

    first = played[0]
    assert (first.source, first.start, first.end) == (grace, _Q - _S, _Q)


@pytest.mark.unit
def test_a_rest_in_a_group_of_grace_notes_is_a_silence_the_next_grace_note_waits_for() -> None:
    score, host, _quarter = _rest_then_a_quarter()
    group: GraceGroup = GraceGroup.create(
        leaf=host, grace_type=GraceType.APPOGGIATURA, placement=GracePlacement.BEFORE
    )
    silent: GraceItem = GraceItem.create(
        grace_group=group, rhythmic_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH)
    )
    Rest.create(rest_carrier=RestCarrier.create(owner=silent), staff=score.staff)
    sounding: GraceItem = GraceItem.create(
        grace_group=group, rhythmic_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH)
    )
    grace: Note = Note.create(
        note_carrier=NoteCarrier.create(owner=sounding),
        staff=score.staff,
        staff_step=-2,
        accidental=Accidental.NATURAL,
    )

    played: list[PlayedNote] = _played_with_rests(document=score.document)

    first = played[0]
    assert (first.source, first.start, first.end) == (grace, _S, 2 * _S)
