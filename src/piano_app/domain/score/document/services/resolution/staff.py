from fractions import Fraction

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.services.geometry import Point, Span, footprint
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves


def resolve_staff(*, geometry: ScoreGeometry, voice: Voice, gap: Span) -> Staff:
    """The staff for a rest the system creates in a gap of a voice.

    It is the staff the voice sounds on longest in the bar the gap starts in — notes and
    rests alike, each for its part inside the bar, a chord on two staves counting on
    both. Of staves sounding equally long, the one holding the element nearest to the gap
    wins, the earlier on equal distance; so a bar holding nothing of the voice takes the
    staff of the nearest element around it. Only the staff is chosen — where on it the
    rest is drawn is the renderer's.

    Raises ``ValueError`` when the gap lies past the last measure or the voice holds
    nothing to take a staff from; refusing the edit is the caller's call.
    """
    on_timeline: Span = gap.to(frame=geometry.root)
    start: Point = on_timeline.start_point

    measure: Measure | None = geometry.measure_at(point=start)
    if measure is None:
        raise ValueError(f"Gap at {start.value} lies past the last measure.")
    bar: Span = footprint(frame=geometry.of_measure(measure=measure))

    sounding: dict[Staff, Fraction] = {}
    # per staff: how far its nearest element lies from the gap, then where it starts
    nearest: dict[Staff, tuple[Fraction, Fraction]] = {}

    for leaf in iter_leaves(voice):
        # in note order, so a full tie settles on the staff of the chord's first note
        staves: list[Staff] = []
        carrier: Carrier | None = leaf.carrier
        if isinstance(carrier, NoteCarrier):
            staves.extend(dict.fromkeys(note.staff for note in carrier.notes))
        elif isinstance(carrier, RestCarrier) and carrier.rest is not None:
            staves.append(carrier.rest.staff)

        span: Span = geometry.global_span_of(container=leaf)
        # what lies outside the bar sounds there for nothing, but still counts as a
        # neighbour of the gap
        inside: Span | None = span.intersection(bar)
        inside_length: Fraction = inside.length if inside is not None else Fraction(0)
        distance: Fraction = max(
            span.start - on_timeline.end,
            on_timeline.start - span.end,
            Fraction(0),
        )

        for staff in staves:
            sounding[staff] = sounding.get(staff, Fraction(0)) + inside_length
            nearest[staff] = min(
                nearest.get(staff, (distance, span.start)),
                (distance, span.start),
            )

    if not sounding:
        raise ValueError("The voice has no element to place a rest by.")

    return min(sounding, key=lambda staff: (-sounding[staff], nearest[staff]))
