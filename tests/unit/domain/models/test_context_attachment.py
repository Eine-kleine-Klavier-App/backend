import pytest

from piano_app.domain.score.document.models.context import ClefChange, DynamicChange, Hairpin
from piano_app.domain.score.document.models.notation import Clef, DynamicMarking
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


# --- Staff <-> StaffPointContext / StaffSpanContext (one-to-many) --------------------


@pytest.mark.unit
def test_creating_a_clef_change_registers_it_on_the_staff(anchor: TemporalAnchor) -> None:
    staff: Staff = Staff()

    clef_change: ClefChange = ClefChange.create(start=anchor, staff=staff, clef=Clef.BASS)

    assert clef_change in staff.contexts


@pytest.mark.unit
def test_deleting_a_clef_change_unregisters_it_from_the_staff(anchor: TemporalAnchor) -> None:
    staff: Staff = Staff()
    clef_change: ClefChange = ClefChange.create(start=anchor, staff=staff, clef=Clef.BASS)

    clef_change.detach()

    assert clef_change not in staff.contexts


@pytest.mark.unit
def test_a_staff_accumulates_several_contexts(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    staff: Staff = Staff()
    first: ClefChange = ClefChange.create(start=anchor, staff=staff, clef=Clef.TREBLE)
    second: ClefChange = ClefChange.create(start=another_anchor, staff=staff, clef=Clef.BASS)

    assert set(staff.contexts) == {first, second}


@pytest.mark.unit
def test_a_context_cannot_be_added_to_a_staff_it_is_not_scoped_to(anchor: TemporalAnchor) -> None:
    staff: Staff = Staff()
    other_staff: Staff = Staff()
    clef_change: ClefChange = ClefChange.create(start=anchor, staff=staff, clef=Clef.BASS)

    with pytest.raises(ValueError, match="another staff"):
        other_staff.add_context(context=clef_change)


# --- Voice <-> VoicePointContext / VoiceSpanContext (one-to-many) --------------------


@pytest.mark.unit
def test_creating_a_dynamic_change_registers_it_on_its_voice(anchor: TemporalAnchor) -> None:
    v1, v2 = Voice(), Voice()

    dynamic_change: DynamicChange = DynamicChange.create(
        start=anchor, voice=v1, dynamic=DynamicMarking.FORTE
    )

    assert dynamic_change in v1.contexts
    assert dynamic_change not in v2.contexts


@pytest.mark.unit
def test_deleting_a_dynamic_change_unregisters_it_from_its_voice(anchor: TemporalAnchor) -> None:
    v1 = Voice()
    dynamic_change: DynamicChange = DynamicChange.create(
        start=anchor, voice=v1, dynamic=DynamicMarking.FORTE
    )

    dynamic_change.detach()

    assert dynamic_change not in v1.contexts


@pytest.mark.unit
def test_a_voice_can_carry_several_contexts_independently(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    """The many-side of the relationship: one voice named by two different contexts, each
    context naming one voice — neither list confuses the other's membership."""
    v1, v2 = Voice(), Voice()
    first: DynamicChange = DynamicChange.create(
        start=anchor, voice=v1, dynamic=DynamicMarking.FORTE
    )
    second: DynamicChange = DynamicChange.create(
        start=another_anchor, voice=v1, dynamic=DynamicMarking.PIANO
    )
    other: DynamicChange = DynamicChange.create(
        start=anchor, voice=v2, dynamic=DynamicMarking.FORTE
    )

    assert set(v1.contexts) == {first, second}
    assert set(v2.contexts) == {other}

    first.detach()

    assert set(v1.contexts) == {second}
    assert set(v2.contexts) == {other}


@pytest.mark.unit
def test_a_context_cannot_be_added_to_a_voice_it_does_not_name(anchor: TemporalAnchor) -> None:
    named, unnamed = Voice(), Voice()
    dynamic_change: DynamicChange = DynamicChange.create(
        start=anchor, voice=named, dynamic=DynamicMarking.FORTE
    )

    with pytest.raises(ValueError, match="does not name this voice"):
        unnamed.add_context(context=dynamic_change)


@pytest.mark.unit
def test_span_voice_context_attaches_to_its_voice_too(
    anchor: TemporalAnchor,
    another_anchor: TemporalAnchor,
) -> None:
    """VoiceSpanContext chains through SpanContext (start+end) as well as its own voice
    wiring -- all three must be live at once."""
    v1 = Voice()

    hairpin: Hairpin = Hairpin.create(
        start=anchor,
        end=another_anchor,
        voice=v1,
        steps=1,
    )

    assert hairpin in v1.contexts
    assert hairpin in anchor.starting_contexts
    assert hairpin in another_anchor.ending_contexts

    hairpin.detach()

    assert hairpin not in v1.contexts
    assert hairpin not in anchor.starting_contexts
    assert hairpin not in another_anchor.ending_contexts
