import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import (
    Carrier,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Point, Span, footprint, gaps
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at, iter_leaves
from piano_app.domain.score.document.services.resolution import resolve_staff

from ..scene import Piano, build_piano, size, with_start_contexts

# `resolve_staff` reads the gap's measure and then only as far around it as an element could
# still decide. It must answer exactly as the full scan over every leaf of the voice did,
# kept below as the oracle. Scenes hold one voice on two staffs.

_Q: Fraction = Fraction(1, 4)


def _full_scan_staff(*, geometry: ScoreGeometry, voice: Voice, gap: Span) -> Staff:
    """The full-scan `resolve_staff` this search replaced, unchanged."""
    on_timeline: Span = gap.to(frame=geometry.root)
    start: Point = on_timeline.start_point

    measure: Measure | None = geometry.measure_at(point=start)
    if measure is None:
        raise ValueError(f"Gap at {start.value} lies past the last measure.")
    measure_region: Span = footprint(frame=geometry.of_measure(measure=measure))

    sounding: defaultdict[Staff, Fraction] = defaultdict(Fraction)
    nearest: dict[Staff, tuple[Fraction, Fraction]] = {}

    for leaf in iter_leaves(voice):
        staffs: list[Staff] = []
        carrier: Carrier | None = leaf.carrier
        if isinstance(carrier, NoteCarrier):
            for note in carrier.notes:
                if note.staff not in staffs:
                    staffs.append(note.staff)
        elif isinstance(carrier, RestCarrier) and carrier.rest is not None:
            staffs.append(carrier.rest.staff)

        span: Span = geometry.global_span_of(container=leaf)
        inside: Span | None = span.intersection(measure_region)
        inside_length: Fraction = inside.length if inside is not None else Fraction(0)
        distance: Fraction = max(
            span.start - on_timeline.end,
            on_timeline.start - span.end,
        )

        for staff in staffs:
            sounding[staff] += inside_length
            nearest[staff] = min(
                nearest.get(staff, (distance, span.start)),
                (distance, span.start),
            )

    if not sounding:
        raise ValueError("The voice has no element to place a rest by.")

    return min(sounding, key=lambda staff: (-sounding[staff], nearest[staff]))


def _anchor_at(*, piano: Piano, at: Fraction) -> TemporalAnchor:
    """The anchor at a timeline position over measures of any signatures, reused when it
    already exists."""
    measure_start: Fraction = Fraction(0)
    for measure in piano.measures:
        if at < measure_start + measure.time_signature.fraction:
            position: MeasurePosition = MeasurePosition.of_fraction(fraction=at - measure_start)
            existing: TemporalAnchor | None = find_anchor_at(measure=measure, position=position)
            return existing or TemporalAnchor.create(measure=measure, position=position)
        measure_start += measure.time_signature.fraction

    raise ValueError(f"{at} lies past the last measure.")


def _leaf(
    *,
    piano: Piano,
    parent: RhythmicContainerParent,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    staffs: Sequence[Staff],
    is_rest: bool = False,
) -> None:
    """A leaf holding a chord with one note per staff listed, or a rest on the first staff
    listed; with no staff listed, a bare leaf."""
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=parent,
        anchor=_anchor_at(piano=piano, at=at),
        size=size(rhythmic_value),
    )
    if not staffs:
        return

    if is_rest:
        Rest.create(rest_carrier=RestCarrier.create(owner=leaf), staff=staffs[0])
        return

    carrier: NoteCarrier = NoteCarrier.create(owner=leaf)
    for step, staff in enumerate(staffs):
        Note.create(
            note_carrier=carrier,
            staff=staff,
            staff_step=step,
            accidental=Accidental.NATURAL,
        )


def _random_leaf(
    *,
    rng: random.Random,
    piano: Piano,
    parent: RhythmicContainerParent,
    at: Fraction,
    rhythmic_value: RhythmicValue,
) -> None:
    """A chord on either or both staffs in either note order, a rest, a bare leaf, or
    nothing."""
    kind: str = rng.choice(["chord", "chord", "chord", "rest", "bare", "none"])
    if kind == "none":
        return

    staffs: list[Staff] = []
    if kind == "chord":
        staffs = rng.choice(
            [
                [piano.upper],
                [piano.lower],
                [piano.upper, piano.lower],
                [piano.lower, piano.upper],
            ]
        )
    elif kind == "rest":
        staffs = [rng.choice([piano.upper, piano.lower])]
    _leaf(
        piano=piano,
        parent=parent,
        at=at,
        rhythmic_value=rhythmic_value,
        staffs=staffs,
        is_rest=kind == "rest",
    )


def _random_tuplet(
    *,
    rng: random.Random,
    piano: Piano,
    parent: RhythmicContainerParent,
    at: Fraction,
    length: Fraction,
    written: RhythmicValue,
    occupied: RhythmicSize,
    may_nest: bool,
) -> None:
    """Three ``written`` in the room of ``occupied`` of the parent, ``length`` long on the
    timeline: now and then childless, else each slot filled at random — with an eighth
    triplet nested in it when allowed."""
    tuplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=parent,
        anchor=_anchor_at(piano=piano, at=at),
        written_size=size(written, count=3),
        occupied_size=occupied,
    )
    if rng.random() < 0.15:
        return

    for index in range(3):
        slot_at: Fraction = at + index * length / 3
        if may_nest and rng.random() < 0.3:
            _random_tuplet(
                rng=rng,
                piano=piano,
                parent=tuplet,
                at=slot_at,
                length=length / 3,
                written=RhythmicValue.EIGHTH,
                occupied=size(written),
                may_nest=False,
            )
        else:
            _random_leaf(rng=rng, piano=piano, parent=tuplet, at=slot_at, rhythmic_value=written)


def _random_piano(*, seed: int) -> Piano:
    """Eight measures of mixed signatures, filled left to right: holes, quarter chords and
    rests on both staffs, halves and wholes that may cross barlines, eighth triplets,
    quarter triplets with nested ones that may cross a barline, three wholes in the room of
    two crossing two or more, childless tuplets, silent measures."""
    rng: random.Random = random.Random(seed)
    measures: list[Measure] = [
        Measure.create(time_signature=size(RhythmicValue.QUARTER, count=rng.choice([2, 3, 4, 5])))
        for _ in range(8)
    ]
    voice: Voice = Voice()
    upper: Staff = Staff()
    lower: Staff = Staff()
    piano: Piano = Piano(
        document=with_start_contexts(
            ScoreDocument.create(voices=[voice], staffs=[upper, lower], measures=measures)
        ),
        voice=voice,
        upper=upper,
        lower=lower,
        measures=measures,
    )

    measure_starts: list[Fraction] = [Fraction(0)]
    for measure in measures:
        measure_starts.append(measure_starts[-1] + measure.time_signature.fraction)
    end: Fraction = measure_starts[-1]

    at: Fraction = Fraction(0)
    while at < end:
        # a silent measure: nothing of the voice from its start to the next barline
        if at in measure_starts and rng.random() < 0.25:
            at = measure_starts[measure_starts.index(at) + 1]
            continue

        kind: str = rng.choice(
            ["hole", "quarter", "quarter", "half", "whole", "eighths", "triplet", "long"]
        )
        length: Fraction = {
            "half": Fraction(1, 2),
            "whole": Fraction(1),
            "triplet": Fraction(1, 2),
            "long": Fraction(2),
        }.get(kind, _Q)
        if at + length > end:
            kind, length = "hole", _Q

        if kind in ("quarter", "half", "whole"):
            _random_leaf(
                rng=rng,
                piano=piano,
                parent=voice,
                at=at,
                rhythmic_value={
                    "quarter": RhythmicValue.QUARTER,
                    "half": RhythmicValue.HALF,
                    "whole": RhythmicValue.WHOLE,
                }[kind],
            )
        elif kind == "eighths":
            _random_tuplet(
                rng=rng,
                piano=piano,
                parent=voice,
                at=at,
                length=length,
                written=RhythmicValue.EIGHTH,
                occupied=size(RhythmicValue.QUARTER),
                may_nest=False,
            )
        elif kind == "triplet":
            _random_tuplet(
                rng=rng,
                piano=piano,
                parent=voice,
                at=at,
                length=length,
                written=RhythmicValue.QUARTER,
                occupied=size(RhythmicValue.HALF),
                may_nest=True,
            )
        elif kind == "long":
            _random_tuplet(
                rng=rng,
                piano=piano,
                parent=voice,
                at=at,
                length=length,
                written=RhythmicValue.WHOLE,
                occupied=size(RhythmicValue.WHOLE, count=2),
                may_nest=False,
            )
        at += length

    return piano


def _holes(*, geometry: ScoreGeometry, voice: Voice) -> list[Span]:
    """Every hole of every scope in every measure, a silent measure whole: the voice's own
    in the timeline, a group's in its own frame."""
    holes: list[Span] = []
    pending: list[RhythmicContainerParent] = [voice]
    while pending:
        scope: RhythmicContainerParent = pending.pop()
        covered: list[Span] = [span for _, span in geometry.contents_of(scope=scope)]
        reach: Span | None = (
            geometry.global_span_of(container=scope)
            if isinstance(scope, GroupRhythmicContainer)
            else None
        )
        for _, region in geometry.measure_regions():
            part: Span | None = region if reach is None else region.intersection(reach)
            if part is not None:
                holes.extend(
                    gaps(bucket=part.to(frame=geometry.of_scope(scope=scope)), covered=covered)
                )
        for child in scope.children:
            if isinstance(child, GroupRhythmicContainer):
                pending.append(child)

    return holes


def _answer(
    *,
    staff_of: Callable[..., Staff],
    piano: Piano,
    geometry: ScoreGeometry,
    gap: Span,
) -> str:
    """The staff by name — its repr would reach the whole score — or the refusal's message."""
    try:
        staff: Staff = staff_of(geometry=geometry, voice=piano.voice, gap=gap)
    except ValueError as error:
        return str(error)

    return "upper" if staff is piano.upper else "lower"


@pytest.mark.unit
@pytest.mark.parametrize("seed", range(80))
def test_the_search_answers_as_the_full_scan_for_every_hole(seed: int) -> None:
    piano: Piano = _random_piano(seed=seed)
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    holes: list[Span] = _holes(geometry=geometry, voice=piano.voice)
    assert holes

    for hole in holes:
        # answers taken outside the assert: pytest would print the scene in its arguments
        searched: str = _answer(staff_of=resolve_staff, piano=piano, geometry=geometry, gap=hole)
        scanned: str = _answer(staff_of=_full_scan_staff, piano=piano, geometry=geometry, gap=hole)
        assert searched == scanned, f"hole at {hole.start}"


@pytest.mark.unit
def test_a_full_tie_goes_to_the_staff_the_voice_met_first() -> None:
    """The voice meets the lower staff first, measures before a chord written upper first;
    the chord alone in its measure ties both staffs on time and distance, and the full scan
    settled it on the staff it met first in the whole voice."""
    piano: Piano = build_piano(measure_count=4)
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.lower],
    )
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=Fraction(3),
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.upper, piano.lower],
    )
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)
    gap: Span = Span(frame=geometry.root, start=3 + _Q, length=3 * _Q)

    searched: str = _answer(staff_of=resolve_staff, piano=piano, geometry=geometry, gap=gap)
    scanned: str = _answer(staff_of=_full_scan_staff, piano=piano, geometry=geometry, gap=gap)
    assert (searched, scanned) == ("lower", "lower")


@pytest.mark.unit
def test_a_gap_measures_away_from_everything_takes_the_staff_of_the_nearest_element() -> None:
    """A quarter above in the first measure, a quarter below in the fifth, nothing between:
    a quarter gap in the second measure lies nearer the one above, one in the fourth nearer
    the one below, and one on beat one of the third, 7/4 from both, goes to the earlier."""
    piano: Piano = build_piano(measure_count=5)
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.upper],
    )
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=Fraction(4),
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.lower],
    )
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    for start, expected in [
        (Fraction(1), "upper"),
        (Fraction(3), "lower"),
        (Fraction(2), "upper"),
    ]:
        gap: Span = Span(frame=geometry.root, start=start, length=_Q)
        searched: str = _answer(staff_of=resolve_staff, piano=piano, geometry=geometry, gap=gap)
        assert searched == expected


@pytest.mark.unit
def test_an_element_before_the_gap_found_last_still_wins_on_equal_distance() -> None:
    """A quarter gap on beat two of the third measure, 5/4 from a quarter below on beat four
    of the fourth measure and 5/4 from a quarter above on beat four of the first. The one
    below is found a measure sooner; the one above, starting earlier, still wins the tie."""
    piano: Piano = build_piano(measure_count=4)
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=3 * _Q,
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.upper],
    )
    _leaf(
        piano=piano,
        parent=piano.voice,
        at=3 + 3 * _Q,
        rhythmic_value=RhythmicValue.QUARTER,
        staffs=[piano.lower],
    )
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)
    gap: Span = Span(frame=geometry.root, start=2 + _Q, length=_Q)

    searched: str = _answer(staff_of=resolve_staff, piano=piano, geometry=geometry, gap=gap)
    scanned: str = _answer(staff_of=_full_scan_staff, piano=piano, geometry=geometry, gap=gap)
    assert (searched, scanned) == ("upper", "upper")
