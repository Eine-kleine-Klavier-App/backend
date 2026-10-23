from collections import defaultdict
from fractions import Fraction

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Point, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry


def resolve_staff(*, geometry: ScoreGeometry, voice: Voice, gap: Span) -> Staff:
    """The staff for a rest the system creates in a gap of a voice.

    It is the staff the voice sounds on longest in the measure the gap starts in — notes and
    rests alike, each for its part inside the measure, a chord on two staffs counting on
    both. Of staffs sounding equally long, the one holding the element nearest to the gap
    wins, the earlier on equal distance; so a measure holding nothing of the voice takes the
    staff of the nearest element around it. Only the staff is chosen — where on it the
    rest is drawn is the renderer's.

    Reads the gap's measure, then the measures around it only as far as an element there
    could still be nearer than the ones deciding.

    Raises ``ValueError`` when the gap lies past the last measure or the voice holds
    nothing to take a staff from; refusing the edit is the caller's call.
    """
    on_timeline: Span = gap.to(frame=geometry.root)
    start: Point = on_timeline.start_point

    measure: Measure | None = geometry.measure_at(point=start)
    if measure is None:
        raise ValueError(f"Gap at {start.value} lies past the last measure.")
    measure_region: Span = geometry.measure_span(measure=measure)

    # only what reaches into the measure sounds there, each for its part inside it
    sounding: defaultdict[Staff, Fraction] = defaultdict(Fraction)
    for leaf in _find_leaves_in(geometry=geometry, scope=voice, measure=measure):
        inside: Span | None = geometry.global_span_of(container=leaf).intersection(measure_region)
        if inside is not None:
            for staff in _staffs_of(leaf=leaf):
                sounding[staff] += inside.length

    # the staffs left to settle by distance: those sounding longest, all met in the measure;
    # none listed when nothing sounds there, for then every staff of the voice is one
    longest: Fraction = max(sounding.values(), default=Fraction(0))
    candidates: list[Staff] = [staff for staff in sounding if sounding[staff] == longest]

    # per staff: how far its nearest element lies from the gap, then where it starts
    nearest: dict[Staff, tuple[Fraction, Fraction]] = {}

    visiting: list[Measure] = [measure]
    earlier: Measure | None = measure.prev_measure
    later: Measure | None = measure.next_measure
    while visiting:
        for visited in visiting:
            for leaf in _find_leaves_in(geometry=geometry, scope=voice, measure=visited):
                span: Span = geometry.global_span_of(container=leaf)
                distance: Fraction = max(
                    span.start - on_timeline.end,
                    on_timeline.start - span.end,
                )
                for staff in _staffs_of(leaf=leaf):
                    nearest[staff] = min(
                        nearest.get(staff, (distance, span.start)),
                        (distance, span.start),
                    )

        # how near an element not read yet would have to lie to change the answer: every
        # candidate is settled once nothing unread can be as near as its own nearest; with
        # no candidate, only the nearest element of all decides
        reach: Fraction | None = None
        if candidates:
            reach = max(nearest[staff][0] for staff in candidates)
        elif nearest:
            reach = min(nearest_distance for nearest_distance, _ in nearest.values())

        # whatever is unread on a side lies wholly beyond the next measure's near edge
        visiting = []
        # unread on the earlier side starts before everything read, so it wins on equal
        # distance and must be read until it would be strictly farther
        if earlier is not None and (
            reach is None or on_timeline.start - geometry.measure_span(measure=earlier).end <= reach
        ):
            visiting.append(earlier)
            earlier = earlier.prev_measure
        # unread on the later side starts after everything read, so it loses on equal distance
        if later is not None and (
            reach is None or geometry.measure_span(measure=later).start - on_timeline.end < reach
        ):
            visiting.append(later)
            later = later.next_measure

    contenders: list[Staff] = candidates or list(nearest)
    if not contenders:
        raise ValueError("The voice has no element to place a rest by.")

    closest: tuple[Fraction, Fraction] = min(nearest[staff] for staff in contenders)
    tied: list[Staff] = [staff for staff in contenders if nearest[staff] == closest]
    if len(tied) == 1:
        return tied[0]

    # a full tie goes to the staff the voice meets first, read from its start — in note
    # order within a chord
    met: list[Staff] = []
    walked: Measure | None = voice.children[0].start_anchor.measure
    while walked is not None and not met:
        for leaf in _find_leaves_in(geometry=geometry, scope=voice, measure=walked):
            for staff in _staffs_of(leaf=leaf):
                if staff in tied:
                    met.append(staff)
        walked = walked.next_measure

    return met[0]


def _find_leaves_in(
    *,
    geometry: ScoreGeometry,
    scope: RhythmicContainerParent,
    measure: Measure,
) -> list[LeafRhythmicContainer]:
    """The scope's leaves reaching into the measure, at any depth, in the scope's order."""
    leaves: list[LeafRhythmicContainer] = []
    for child, _ in geometry.contents_in(scope=scope, measure=measure):
        if isinstance(child, LeafRhythmicContainer):
            leaves.append(child)
        elif isinstance(child, GroupRhythmicContainer):
            leaves.extend(_find_leaves_in(geometry=geometry, scope=child, measure=measure))
        else:
            raise TypeError(f"Unsupported rhythmic container type: {type(child).__name__}.")

    return leaves


def _staffs_of(*, leaf: LeafRhythmicContainer) -> list[Staff]:
    """The staffs a leaf sounds on, in note order."""
    staffs: list[Staff] = []
    carrier: Carrier | None = leaf.carrier
    if isinstance(carrier, NoteCarrier):
        for note in carrier.notes:
            if note.staff not in staffs:
                staffs.append(note.staff)
    elif isinstance(carrier, RestCarrier) and carrier.rest is not None:
        staffs.append(carrier.rest.staff)

    return staffs
