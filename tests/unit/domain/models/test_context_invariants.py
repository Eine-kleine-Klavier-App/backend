import pytest

from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    KeySignatureSymbol,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.context.point.score import TempoChange
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DynamicMarking,
    HairpinType,
    TempoMarking,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)


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


# --- TempoChange: bpm/marking, at least one required ---------------------------------


@pytest.mark.unit
def test_tempo_change_accepts_marking_alone(anchor: TemporalAnchor) -> None:
    tempo: TempoChange = TempoChange.create(start=anchor, marking=TempoMarking.ALLEGRO)
    assert tempo.bpm is None and tempo.marking is TempoMarking.ALLEGRO


@pytest.mark.unit
def test_tempo_change_accepts_bpm_alone(anchor: TemporalAnchor) -> None:
    tempo: TempoChange = TempoChange.create(start=anchor, bpm=120)
    assert tempo.marking is None and tempo.bpm == 120


@pytest.mark.unit
def test_tempo_change_rejects_neither(anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="BPM, a marking, or both"):
        TempoChange.create(start=anchor)


@pytest.mark.unit
def test_tempo_change_still_rejects_a_non_positive_bpm(anchor: TemporalAnchor) -> None:
    with pytest.raises(ValueError, match="at least 1 BPM"):
        TempoChange.create(start=anchor, bpm=0)


# --- KeySignatureSymbol / KeySignatureChange: no duplicate step ---
# (NONE/NATURAL accidentals are no longer representable here at all — enforced by
# KeySignatureAccidental's type, not a runtime check.)


@pytest.mark.unit
def test_key_signature_change_rejects_duplicate_staff_step(
    anchor: TemporalAnchor,
    staff: Staff,
) -> None:
    with pytest.raises(ValueError, match="not repeat a staff step"):
        KeySignatureChange.create(
            start=anchor,
            staff=staff,
            symbols=(
                KeySignatureSymbol(staff_step=3, accidental=Accidental.SHARP),
                KeySignatureSymbol(staff_step=3, accidental=Accidental.FLAT),
            ),
        )


@pytest.mark.unit
def test_key_signature_change_accepts_distinct_steps(anchor: TemporalAnchor, staff: Staff) -> None:
    change: KeySignatureChange = KeySignatureChange.create(
        start=anchor,
        staff=staff,
        symbols=(
            KeySignatureSymbol(staff_step=3, accidental=Accidental.SHARP),
            KeySignatureSymbol(staff_step=6, accidental=Accidental.SHARP),
        ),
    )
    assert len(change.symbols) == 2


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


# --- Hairpin: now carries a direction ---------------------------------------------------


@pytest.mark.unit
def test_hairpin_carries_its_direction(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    voice: Voice = Voice()
    hairpin: Hairpin = Hairpin.create(
        start=anchor,
        end=another_anchor,
        voices=[voice],
        hairpin_type=HairpinType.CRESCENDO,
    )
    assert hairpin.hairpin_type is HairpinType.CRESCENDO


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
            hairpin_type=HairpinType.DIMINUENDO,
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
            hairpin_type=HairpinType.CRESCENDO,
        )
