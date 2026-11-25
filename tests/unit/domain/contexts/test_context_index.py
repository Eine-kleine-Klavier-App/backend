from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    OctaveTransposition,
    Slur,
    TempoChange,
)
from piano_app.domain.score.document.models.notation import (
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry import Piece
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import IndexLayer
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

# three measures of one whole note: the timeline runs from 0 to 3
_ONE: Fraction = Fraction(1)
_TWO: Fraction = Fraction(2)
_THREE: Fraction = Fraction(3)
_HALF: Fraction = Fraction(1, 2)


def _document() -> ScoreDocument:
    """Three measures, two staffs, two voices, and the contexts a score starts with."""
    return ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=3)


def _index(*, document: ScoreDocument) -> ContextIndex:
    return ContextIndex(document=document, geometry=ScoreGeometry(document=document))


def _shape[T](piece: Piece[T | None, T]) -> tuple[Fraction, Fraction, T | None]:
    """Where a piece starts, where it ends, and what it answers with."""
    return piece.span.start, piece.span.end, piece.value


def test_the_piece_at_a_point_is_the_clef_in_force_up_to_the_next_one() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    treble: ClefChange = next(
        clef
        for clef in upper.contexts
        if isinstance(clef, ClefChange) and clef.start.measure is document.measures[0]
    )
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=upper, clef=Clef.BASS)
    index: ContextIndex = _index(document=document)

    before: Piece[ClefChange | None, ClefChange] = index.piece_at(
        kind=ClefChange, point=_HALF, scope=Scope.of_staff(staff=upper)
    )
    after: Piece[ClefChange | None, ClefChange] = index.piece_at(
        kind=ClefChange, point=Fraction(3, 2), scope=Scope.of_staff(staff=upper)
    )

    assert _shape(before) == (Fraction(0), _ONE, treble)
    assert before.sources == (treble,)
    assert _shape(after) == (_ONE, _THREE, bass)


def test_on_a_boundary_the_piece_that_starts_there_wins() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=upper, clef=Clef.BASS)

    piece: Piece[ClefChange | None, ClefChange] = _index(document=document).piece_at(
        kind=ClefChange, point=_ONE, scope=Scope.of_staff(staff=upper)
    )

    assert piece.value is bass


def test_before_the_first_context_of_its_kind_nothing_holds() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=1, measure_count=3
    )
    for tempo in [
        context
        for context in document.measures[0].anchors[0].starting_contexts
        if isinstance(context, TempoChange)
    ]:
        tempo.detach()
    later: TempoChange = TempoChange.create(
        start=anchor(document, _ONE),
        beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
        bpm=100,
    )

    piece: Piece[TempoChange | None, TempoChange] = _index(document=document).piece_at(
        kind=TempoChange, point=_HALF, scope=Scope.score()
    )

    assert _shape(piece) == (Fraction(0), _ONE, None)
    assert piece.sources == ()
    assert (
        _index(document=document).piece_at(kind=TempoChange, point=_ONE, scope=Scope.score()).value
        is later
    )


def test_the_pieces_over_an_interval_tile_it_exactly_and_are_cut_at_every_source() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=upper, clef=Clef.BASS)
    again: ClefChange = ClefChange.create(
        start=anchor(document, _TWO), staff=upper, clef=Clef.TREBLE
    )

    pieces: list[Piece[ClefChange | None, ClefChange]] = _index(document=document).pieces_over(
        kind=ClefChange, start=_HALF, end=Fraction(5, 2), scope=Scope.of_staff(staff=upper)
    )

    assert [(piece.span.start, piece.span.end) for piece in pieces] == [
        (_HALF, _ONE),
        (_ONE, _TWO),
        (_TWO, Fraction(5, 2)),
    ]
    assert [piece.value for piece in pieces][1:] == [bass, again]
    assert [piece.value.clef for piece in pieces if piece.value is not None] == [
        Clef.TREBLE,
        Clef.BASS,
        Clef.TREBLE,
    ]


def test_a_span_kind_answers_nothing_where_no_span_lies() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _ONE), end=anchor(document, _TWO), staff=upper, octaves=1
    )

    pieces: list[Piece[OctaveTransposition | None, OctaveTransposition]] = _index(
        document=document
    ).pieces_over(
        kind=OctaveTransposition, start=Fraction(0), end=_THREE, scope=Scope.of_staff(staff=upper)
    )

    assert [(piece.span.start, piece.span.end, piece.value) for piece in pieces] == [
        (Fraction(0), _ONE, None),
        (_ONE, _TWO, line),
        (_TWO, _THREE, None),
    ]
    assert [piece.sources for piece in pieces] == [(), (line,), ()]


def test_overlapping_spans_are_all_the_sources_of_the_piece_they_share() -> None:
    document: ScoreDocument = _document()
    voice = document.voices[0]
    outer: Slur = Slur.create(
        start=anchor(document, _ONE), end=anchor(document, _THREE - Fraction(1, 8)), voice=voice
    )
    inner: Slur = Slur.create(
        start=anchor(document, _TWO), end=anchor(document, Fraction(5, 2)), voice=voice
    )

    pieces: list[Piece[Slur | None, Slur]] = _index(document=document).pieces_over(
        kind=Slur, start=_ONE, end=Fraction(23, 8), scope=Scope.of_voice(voice=voice)
    )

    assert [(piece.span.start, piece.span.end) for piece in pieces] == [
        (_ONE, _TWO),
        (_TWO, Fraction(5, 2)),
        (Fraction(5, 2), Fraction(23, 8)),
    ]
    assert [piece.sources for piece in pieces] == [(outer,), (outer, inner), (outer,)]
    assert [piece.value for piece in pieces] == [outer, inner, outer]


def test_each_voice_is_governed_by_its_own_dynamics() -> None:
    document: ScoreDocument = _document()
    first, second = document.voices
    on_first: DynamicChange = DynamicChange.create(
        start=anchor(document, _ONE), voice=first, dynamic=DynamicMarking.FORTE
    )
    on_second: DynamicChange = DynamicChange.create(
        start=anchor(document, _ONE), voice=second, dynamic=DynamicMarking.FORTE
    )
    own: DynamicChange = DynamicChange.create(
        start=anchor(document, _TWO), voice=first, dynamic=DynamicMarking.MEZZO_FORTE
    )
    index: ContextIndex = _index(document=document)

    assert (
        index.piece_at(
            kind=DynamicChange, point=Fraction(3, 2), scope=Scope.of_voice(voice=first)
        ).value
        is on_first
    )
    assert (
        index.piece_at(
            kind=DynamicChange, point=Fraction(5, 2), scope=Scope.of_voice(voice=first)
        ).value
        is own
    )
    assert (
        index.piece_at(
            kind=DynamicChange, point=Fraction(5, 2), scope=Scope.of_voice(voice=second)
        ).value
        is on_second
    )


def test_the_contexts_of_a_kind_that_start_at_a_point_are_found_by_scope() -> None:
    document: ScoreDocument = _document()
    upper, lower = document.staffs
    on_upper: ClefChange = ClefChange.create(
        start=anchor(document, _ONE), staff=upper, clef=Clef.BASS
    )
    on_lower: ClefChange = ClefChange.create(
        start=anchor(document, _ONE), staff=lower, clef=Clef.TREBLE
    )
    index: ContextIndex = _index(document=document)

    assert index.starting_at(kind=ClefChange, point=_ONE, scope=Scope.of_staff(staff=upper)) == [
        on_upper
    ]
    assert index.starting_at(kind=ClefChange, point=_ONE, scope=Scope.of_staff(staff=lower)) == [
        on_lower
    ]
    assert index.starting_at(kind=ClefChange, point=_TWO, scope=Scope.of_staff(staff=upper)) == []


def test_a_point_or_an_interval_outside_the_timeline_is_refused() -> None:
    index: ContextIndex = _index(document=_document())

    with pytest.raises(ValueError, match="outside the timeline"):
        index.piece_at(kind=TempoChange, point=_THREE, scope=Scope.score())

    with pytest.raises(ValueError, match="outside the timeline"):
        index.pieces_over(kind=TempoChange, start=_TWO, end=Fraction(7, 2), scope=Scope.score())


def test_the_index_heals_after_changes_the_journal_reports() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    index: ContextIndex = ContextIndex(document=document, geometry=geometry)
    log: MutationLog = MutationLog()
    log.subscribe(IndexLayer(indexes=(geometry, index)))
    scope: Scope = Scope.of_staff(staff=upper)
    assert index.piece_at(kind=ClefChange, point=Fraction(3, 2), scope=scope).value is not None
    assert index.piece_at(kind=ClefChange, point=Fraction(3, 2), scope=scope).sources[0].clef is (
        Clef.TREBLE
    )

    bass: ClefChange = ClefChange.create(
        start=anchor(document, _ONE), staff=upper, clef=Clef.BASS, sink=log
    )
    assert index.piece_at(kind=ClefChange, point=Fraction(3, 2), scope=scope).value is bass

    bass.set_start(start=anchor(document, _TWO), sink=log)
    assert index.piece_at(kind=ClefChange, point=Fraction(3, 2), scope=scope).value is not bass
    assert index.piece_at(kind=ClefChange, point=Fraction(5, 2), scope=scope).value is bass

    bass.detach(sink=log)
    assert index.piece_at(kind=ClefChange, point=Fraction(5, 2), scope=scope).value is not bass


def test_the_region_of_a_point_runs_to_the_next_of_its_kind_and_of_a_span_to_its_end() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    treble: ClefChange = next(
        clef
        for clef in upper.contexts
        if isinstance(clef, ClefChange) and clef.start.measure is document.measures[0]
    )
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=upper, clef=Clef.BASS)
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _ONE), end=anchor(document, _TWO), staff=upper, octaves=1
    )
    index: ContextIndex = _index(document=document)

    assert (index.region_of(context=treble).start, index.region_of(context=treble).end) == (
        Fraction(0),
        _ONE,
    )
    assert (index.region_of(context=bass).start, index.region_of(context=bass).end) == (
        _ONE,
        _THREE,
    )
    assert (index.region_of(context=line).start, index.region_of(context=line).end) == (_ONE, _TWO)


def test_a_context_of_one_voice_is_governed_up_to_that_voices_next_one() -> None:
    document: ScoreDocument = _document()
    first, second = document.voices
    on_first: DynamicChange = DynamicChange.create(
        start=anchor(document, _ONE), voice=first, dynamic=DynamicMarking.FORTE
    )
    on_second: DynamicChange = DynamicChange.create(
        start=anchor(document, _ONE), voice=second, dynamic=DynamicMarking.FORTE
    )
    DynamicChange.create(
        start=anchor(document, _TWO), voice=first, dynamic=DynamicMarking.MEZZO_FORTE
    )
    index: ContextIndex = _index(document=document)

    assert index.region_of(context=on_first).end == _TWO
    assert index.region_of(context=on_second).end == _THREE


def test_the_contexts_of_a_kind_come_by_where_they_start_and_all_of_them_in_measure_order() -> None:
    document: ScoreDocument = _document()
    upper = document.staffs[0]
    later: ClefChange = ClefChange.create(
        start=anchor(document, _TWO), staff=upper, clef=Clef.TREBLE
    )
    earlier: ClefChange = ClefChange.create(
        start=anchor(document, _ONE), staff=upper, clef=Clef.BASS
    )
    index: ContextIndex = _index(document=document)

    of_upper: list[ClefChange] = index.contexts_of(
        kind=ClefChange, scope=Scope.of_staff(staff=upper)
    )
    everything: list[object] = list(index.contexts())

    assert of_upper[1:] == [earlier, later]
    assert everything.index(earlier) < everything.index(later)
    assert len(everything) == len(
        [
            context
            for measure in document.measures
            for each in measure.anchors
            for context in each.starting_contexts
        ]
    )
