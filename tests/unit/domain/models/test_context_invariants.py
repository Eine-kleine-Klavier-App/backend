from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import (
    NO_ACCIDENTALS,
    ClefChange,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    OctaveTransposition,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    HairpinType,
    RhythmicValue,
    TempoMarking,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)

_QUARTER: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)


@pytest.fixture
def anchor() -> TemporalAnchor:
    measure: Measure = Measure.create()
    position: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)
    return TemporalAnchor.create(measure=measure, position=position)


@pytest.fixture
def another_anchor(anchor: TemporalAnchor) -> TemporalAnchor:
    """On the same measure as ``anchor``, at a later position — every span-context
    fixture pairing needs ``start`` to actually precede ``end`` now."""
    position: MeasurePosition = MeasurePosition.of(numerator=1, denominator=2)
    return TemporalAnchor.create(measure=anchor.measure, position=position)


@pytest.fixture
def staff() -> Staff:
    return Staff()


# --- TempoChange: a beat and a number of them per minute ---------------------------------


@pytest.mark.unit
def test_tempo_change_holds_its_beat_number_and_label(anchor: TemporalAnchor) -> None:
    dotted: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.EIGHTH, dots_count=1)

    tempo: TempoChange = TempoChange.create(start=anchor, beat=dotted, bpm=96, show_label=True)

    assert (tempo.beat, tempo.bpm, tempo.label) == (dotted, 96, TempoMarking.ADAGIO)


@pytest.mark.unit
def test_tempo_change_needs_no_label(anchor: TemporalAnchor) -> None:
    assert TempoChange.create(start=anchor, beat=_QUARTER, bpm=120).label is None


@pytest.mark.unit
@pytest.mark.parametrize("bpm", [0, -5])
def test_tempo_change_rejects_a_non_positive_number(anchor: TemporalAnchor, bpm: int) -> None:
    with pytest.raises(ValueError, match="at least 1 beat per minute"):
        TempoChange.create(start=anchor, beat=_QUARTER, bpm=bpm)


@pytest.mark.unit
def test_every_tempo_word_has_a_typical_number_inside_its_usual_range() -> None:
    ranges: dict[TempoMarking, tuple[int, int]] = {
        TempoMarking.GRAVE: (20, 40),
        TempoMarking.LARGO: (40, 60),
        TempoMarking.ADAGIO: (66, 76),
        TempoMarking.ANDANTE: (76, 108),
        TempoMarking.MODERATO: (108, 120),
        TempoMarking.ALLEGRO: (120, 156),
        TempoMarking.PRESTO: (168, 200),
    }

    assert set(ranges) == set(TempoMarking)
    for marking, (low, high) in ranges.items():
        assert abs(marking.typical_bpm - (low + high) / 2) <= 0.5, marking


# --- KeySignatureChange: seven alterations, one for each diatonic step -------------------


@pytest.mark.unit
def test_key_signature_change_defaults_to_naturals_everywhere(
    anchor: TemporalAnchor, staff: Staff
) -> None:
    change: KeySignatureChange = KeySignatureChange.create(start=anchor, staff=staff)

    assert change.alterations == NO_ACCIDENTALS
    assert len(change.alterations) == 7


@pytest.mark.unit
def test_key_signature_change_holds_the_alterations_it_is_given(
    anchor: TemporalAnchor, staff: Staff
) -> None:
    one_sharp: tuple[Accidental, ...] = (
        *(Accidental.NATURAL,) * 3,
        Accidental.SHARP,
        *(Accidental.NATURAL,) * 3,
    )

    change: KeySignatureChange = KeySignatureChange.create(
        start=anchor, staff=staff, alterations=one_sharp
    )

    assert change.alterations == one_sharp


@pytest.mark.unit
@pytest.mark.parametrize("count", [0, 6, 8])
def test_key_signature_change_rejects_a_wrong_number_of_alterations(
    anchor: TemporalAnchor, staff: Staff, count: int
) -> None:
    with pytest.raises(ValueError, match="7 alterations"):
        KeySignatureChange.create(
            start=anchor, staff=staff, alterations=(Accidental.SHARP,) * count
        )


# --- ClefChange: octave transposition is an unbounded field ---------------------------


@pytest.mark.unit
def test_clef_change_accepts_any_octave_transposition(
    anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    clef_change: ClefChange = ClefChange.create(
        start=anchor, staff=staff, clef=Clef.TREBLE, octave_transposition=99
    )
    assert clef_change.octave_transposition == 99


# --- OctaveTransposition (span): now carries octaves, and it must be nonzero ----------


@pytest.mark.unit
def test_octave_transposition_requires_a_real_amount(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    with pytest.raises(ValueError, match="1 or 2 octaves"):
        OctaveTransposition.create(start=anchor, end=another_anchor, staff=staff, octaves=0)


@pytest.mark.unit
def test_octave_transposition_rejects_more_than_two_octaves(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    with pytest.raises(ValueError, match="1 or 2 octaves"):
        OctaveTransposition.create(start=anchor, end=another_anchor, staff=staff, octaves=3)


@pytest.mark.unit
def test_octave_transposition_accepts_a_signed_octave_or_two(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    down: OctaveTransposition = OctaveTransposition.create(
        start=anchor, end=another_anchor, staff=staff, octaves=-1
    )
    assert down.octaves == -1


@pytest.mark.unit
def test_octave_transposition_still_rejects_identical_start_and_end(
    anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    """The inherited SpanContext check must survive the new __post_init__ chaining
    through super()."""
    with pytest.raises(ValueError, match="must precede end"):
        OctaveTransposition.create(start=anchor, end=anchor, staff=staff, octaves=1)


# --- Hairpin: a number of dynamic levels, the direction follows its sign -----------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("steps", "expected"),
    [(3, HairpinType.CRESCENDO), (1, HairpinType.CRESCENDO), (-2, HairpinType.DIMINUENDO)],
)
def test_hairpin_direction_follows_the_sign_of_its_steps(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
    steps: int,
    expected: HairpinType,
) -> None:
    hairpin: Hairpin = Hairpin.create(
        start=anchor, end=another_anchor, voices=[Voice()], steps=steps
    )

    assert (hairpin.steps, hairpin.hairpin_type) == (steps, expected)


@pytest.mark.unit
def test_hairpin_rejects_zero_steps(anchor: TemporalAnchor, another_anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="at least one level"):
        Hairpin.create(start=anchor, end=another_anchor, voices=[Voice()], steps=0)


@pytest.mark.unit
def test_hairpin_steps_are_changed_in_place_and_never_to_zero(
    anchor: TemporalAnchor, another_anchor: TemporalAnchor
) -> None:
    hairpin: Hairpin = Hairpin.create(start=anchor, end=another_anchor, voices=[Voice()], steps=2)

    hairpin.set_steps(steps=-3)
    assert (hairpin.steps, hairpin.hairpin_type) == (-3, HairpinType.DIMINUENDO)

    with pytest.raises(ValueError, match="at least one level"):
        hairpin.set_steps(steps=0)

    assert hairpin.steps == -3


# --- TempoTransition: a ratio of speed, positive and not one ------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("ratio", [Fraction(7, 9), Fraction(3, 2), Fraction(1, 100)])
def test_tempo_transition_holds_a_ratio_of_speed(
    anchor: TemporalAnchor, another_anchor: TemporalAnchor, ratio: Fraction
) -> None:
    transition: TempoTransition = TempoTransition.create(
        start=anchor, end=another_anchor, ratio=ratio
    )

    assert transition.ratio == ratio


@pytest.mark.unit
@pytest.mark.parametrize("ratio", [Fraction(0), Fraction(-1, 2)])
def test_tempo_transition_rejects_a_non_positive_ratio(
    anchor: TemporalAnchor, another_anchor: TemporalAnchor, ratio: Fraction
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        TempoTransition.create(start=anchor, end=another_anchor, ratio=ratio)


@pytest.mark.unit
def test_tempo_transition_rejects_a_ratio_of_one(
    anchor: TemporalAnchor, another_anchor: TemporalAnchor
) -> None:
    with pytest.raises(ValueError, match="must not be one"):
        TempoTransition.create(start=anchor, end=another_anchor, ratio=Fraction(1))


@pytest.mark.unit
def test_tempo_transition_ratio_is_changed_in_place_under_the_same_rules(
    anchor: TemporalAnchor, another_anchor: TemporalAnchor
) -> None:
    transition: TempoTransition = TempoTransition.create(
        start=anchor, end=another_anchor, ratio=Fraction(1, 2)
    )

    transition.set_ratio(ratio=Fraction(5, 4))
    assert transition.ratio == Fraction(5, 4)

    with pytest.raises(ValueError, match="must not be one"):
        transition.set_ratio(ratio=Fraction(1))

    assert transition.ratio == Fraction(5, 4)


@pytest.mark.unit
def test_tempo_transition_still_rejects_identical_start_and_end(anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="must precede end"):
        TempoTransition.create(start=anchor, end=anchor, ratio=Fraction(1, 2))


# --- DynamicMarking: a scale from the softest to the loudest -----------------------------


@pytest.mark.unit
def test_dynamic_marking_levels_run_from_ppp_to_fff() -> None:
    assert [marking.value for marking in sorted(DynamicMarking, key=lambda m: m.level)] == [
        "ppp",
        "pp",
        "p",
        "mp",
        "mf",
        "f",
        "ff",
        "fff",
    ]
    assert [marking.level for marking in DynamicMarking] == list(range(8))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (-4, DynamicMarking.PIANISSIMISSIMO),
        (0, DynamicMarking.PIANISSIMISSIMO),
        (4, DynamicMarking.MEZZO_FORTE),
        (7, DynamicMarking.FORTISSIMISSIMO),
        (12, DynamicMarking.FORTISSIMISSIMO),
    ],
)
def test_dynamic_marking_at_a_level_is_held_to_the_scale(
    level: int, expected: DynamicMarking
) -> None:
    assert DynamicMarking.at_level(level) is expected


# --- Voices*Context: non-empty, unique voices -------------------------------------------


@pytest.mark.unit
def test_dynamic_change_rejects_an_empty_voice_scope(anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="at least one voice"):
        DynamicChange.create(start=anchor, voices=[], dynamic=DynamicMarking.FORTE)


@pytest.mark.unit
def test_dynamic_change_rejects_a_repeated_voice(anchor: TemporalAnchor) -> None:
    voice: Voice = Voice()
    with pytest.raises(ValueError, match="not repeat a voice"):
        DynamicChange.create(start=anchor, voices=[voice, voice], dynamic=DynamicMarking.FORTE)


@pytest.mark.unit
def test_hairpin_rejects_an_empty_voice_scope(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    with pytest.raises(ValueError, match="at least one voice"):
        Hairpin.create(
            start=anchor,
            end=another_anchor,
            voices=[],
            steps=-1,
        )


@pytest.mark.unit
def test_hairpin_still_rejects_identical_start_and_end_via_the_voices_chain(
    anchor: TemporalAnchor,
) -> None:
    """VoicesSpanContext.__post_init__ must chain to SpanContext's own check too."""
    voice: Voice = Voice()
    with pytest.raises(ValueError, match="must precede end"):
        Hairpin.create(
            start=anchor,
            end=anchor,
            voices=[voice],
            steps=1,
        )


@pytest.mark.unit
def test_a_context_changes_its_voices_keeping_itself(anchor: TemporalAnchor) -> None:
    first, second, third = Voice(), Voice(), Voice()
    dynamic: DynamicChange = DynamicChange.create(
        start=anchor, voices=[first, second], dynamic=DynamicMarking.FORTE
    )

    dynamic.set_voices(voices=[second, third])

    assert dynamic.voices == [second, third]
    assert dynamic not in first.contexts
    assert dynamic in second.contexts and dynamic in third.contexts


@pytest.mark.unit
def test_a_context_cannot_be_left_without_voices_or_with_a_repeated_one(
    anchor: TemporalAnchor,
) -> None:
    voice: Voice = Voice()
    dynamic: DynamicChange = DynamicChange.create(
        start=anchor, voices=[voice], dynamic=DynamicMarking.FORTE
    )

    with pytest.raises(ValueError, match="at least one voice"):
        dynamic.set_voices(voices=[])

    with pytest.raises(ValueError, match="not repeat a voice"):
        dynamic.set_voices(voices=[voice, voice])

    assert dynamic.voices == [voice] and dynamic in voice.contexts
