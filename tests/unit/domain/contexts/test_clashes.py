from fractions import Fraction

from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    Hairpin,
    OctaveTransposition,
    Slur,
    SustainHold,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.notation import (
    Clef,
    DynamicMarking,
)
from piano_app.domain.score.document.services.contexts import (
    Clash,
    ClashKind,
    ContextIndex,
    find_clashes,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

_ONE: Fraction = Fraction(1)
_TWO: Fraction = Fraction(2)
_THREE: Fraction = Fraction(3)
_HALF_PAST_ONE: Fraction = Fraction(3, 2)
_HALF_PAST_TWO: Fraction = Fraction(5, 2)


def _document() -> ScoreDocument:
    """Three measures of one whole note, two staffs, two voices, the starting contexts."""
    return ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=3)


def _index(*, document: ScoreDocument) -> ContextIndex:
    return ContextIndex(document=document, geometry=ScoreGeometry(document=document))


def _kinds(*, clashes: list[Clash]) -> list[ClashKind]:
    return [clash.kind for clash in clashes]


def test_a_point_meets_a_context_of_its_kind_at_its_own_place_on_the_same_staff_only() -> None:
    document: ScoreDocument = _document()
    upper, lower = document.staffs
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=upper, clef=Clef.BASS)
    index: ContextIndex = _index(document=document)

    same: list[Clash] = find_clashes(
        contexts=index, kind=ClefChange, start=_ONE, end=None, staff=upper, voices=None
    )
    other_staff: list[Clash] = find_clashes(
        contexts=index, kind=ClefChange, start=_ONE, end=None, staff=lower, voices=None
    )
    moved: list[Clash] = find_clashes(
        contexts=index, kind=ClefChange, start=_ONE, end=None, staff=upper, voices=None, ignore=bass
    )

    assert [(clash.kind, clash.context) for clash in same] == [(ClashKind.SAME_PLACE, bass)]
    assert other_staff == []
    assert moved == []


def test_a_point_on_voices_meets_a_context_that_shares_a_voice() -> None:
    document: ScoreDocument = _document()
    first, second = document.voices
    shared: DynamicChange = DynamicChange.create(
        start=anchor(document, _ONE), voices=[first, second], dynamic=DynamicMarking.FORTE
    )
    index: ContextIndex = _index(document=document)

    sharing: list[Clash] = find_clashes(
        contexts=index, kind=DynamicChange, start=_ONE, end=None, staff=None, voices=[second]
    )

    assert [clash.context for clash in sharing] == [shared]


def test_a_span_meets_the_spans_of_its_kind_it_overlaps_but_not_one_it_touches() -> None:
    document: ScoreDocument = _document()
    upper, lower = document.staffs
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _ONE), end=anchor(document, _TWO), staff=upper, octaves=1
    )
    index: ContextIndex = _index(document=document)

    over: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=_HALF_PAST_ONE,
        end=_HALF_PAST_TWO,
        staff=upper,
        voices=None,
    )
    touching: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=_TWO,
        end=_THREE,
        staff=upper,
        voices=None,
    )
    other_staff: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=_HALF_PAST_ONE,
        end=_HALF_PAST_TWO,
        staff=lower,
        voices=None,
    )
    moved: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=_HALF_PAST_ONE,
        end=_HALF_PAST_TWO,
        staff=upper,
        voices=None,
        ignore=line,
    )

    assert [(clash.kind, clash.context) for clash in over] == [(ClashKind.OVERLAP, line)]
    assert touching == []
    assert other_staff == []
    assert moved == []


def test_a_span_with_no_end_lasts_to_the_end_of_the_score() -> None:
    document: ScoreDocument = _document()
    upper, _ = document.staffs
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _ONE), end=None, staff=upper, octaves=1
    )
    index: ContextIndex = _index(document=document)

    later: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=_HALF_PAST_TWO,
        end=_THREE,
        staff=upper,
        voices=None,
    )
    before: list[Clash] = find_clashes(
        contexts=index,
        kind=OctaveTransposition,
        start=Fraction(0),
        end=_ONE,
        staff=upper,
        voices=None,
    )

    assert [(clash.kind, clash.context) for clash in later] == [(ClashKind.OVERLAP, line)]
    assert before == []


def test_slurs_are_free_to_overlap() -> None:
    document: ScoreDocument = _document()
    voice = document.voices[0]
    Slur.create(start=anchor(document, _ONE), end=anchor(document, _HALF_PAST_TWO), voices=[voice])

    assert (
        find_clashes(
            contexts=_index(document=document),
            kind=Slur,
            start=_HALF_PAST_ONE,
            end=_HALF_PAST_TWO,
            staff=None,
            voices=[voice],
        )
        == []
    )


def test_a_point_is_inside_a_partner_span_only_strictly_between_its_ends() -> None:
    document: ScoreDocument = _document()
    transition: TempoTransition = TempoTransition.create(
        start=anchor(document, _ONE), end=anchor(document, _TWO), ratio=Fraction(2)
    )
    index: ContextIndex = _index(document=document)

    def clashes_at(point: Fraction) -> list[Clash]:
        """The clashes of a tempo placed at the point that come of the transition."""
        return [
            clash
            for clash in find_clashes(
                contexts=index, kind=TempoChange, start=point, end=None, staff=None, voices=None
            )
            if clash.kind is ClashKind.INSIDE
        ]

    inside: list[Clash] = clashes_at(_HALF_PAST_ONE)
    assert [(clash.kind, clash.context) for clash in inside] == [(ClashKind.INSIDE, transition)]
    assert clashes_at(Fraction(0)) == []
    assert clashes_at(_ONE) == []
    assert clashes_at(_TWO) == []
    assert clashes_at(_HALF_PAST_TWO) == []


def test_a_span_holds_a_partner_point_only_strictly_inside_it_and_on_its_own_voices() -> None:
    document: ScoreDocument = _document()
    first, second = document.voices
    inside: DynamicChange = DynamicChange.create(
        start=anchor(document, _HALF_PAST_ONE), voices=[first], dynamic=DynamicMarking.FORTE
    )
    DynamicChange.create(
        start=anchor(document, _ONE), voices=[first], dynamic=DynamicMarking.MEZZO_FORTE
    )
    DynamicChange.create(
        start=anchor(document, _HALF_PAST_ONE), voices=[second], dynamic=DynamicMarking.PIANO
    )
    index: ContextIndex = _index(document=document)

    held: list[Clash] = find_clashes(
        contexts=index, kind=Hairpin, start=_ONE, end=_TWO, staff=None, voices=[first]
    )

    assert [(clash.kind, clash.context) for clash in held] == [(ClashKind.HOLDS, inside)]


class _WithoutPolicy(SustainHold):
    """A kind the table does not name: every kind of context has a policy today."""


def test_a_kind_without_a_policy_meets_nothing() -> None:
    document: ScoreDocument = _document()
    SustainHold.create(start=anchor(document, _ONE), end=anchor(document, _TWO))

    assert (
        find_clashes(
            contexts=_index(document=document),
            kind=_WithoutPolicy,
            start=_HALF_PAST_ONE,
            end=_HALF_PAST_TWO,
            staff=None,
            voices=None,
        )
        == []
    )
