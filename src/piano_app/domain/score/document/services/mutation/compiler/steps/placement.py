from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Voice
from piano_app.domain.score.document.models.structural.rhythm import RhythmicContainerParent
from piano_app.domain.score.document.services.geometry import Point, Span, overflow
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import RhythmicSizeMapper
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

# Where a new rhythmic item goes, worked out before any request runs. The same path for
# every item, however long: the scope comes from the start, the item must fit in it, the
# measures cut it, and each cut is spelled as values. Whether the parts become tied notes
# or plain rests is the calling compiler's decision, not this one's. An item that is never
# cut — a tuplet — stops after the location.

_SIZE_MAPPER: RhythmicSizeMapper = RhythmicSizeMapper()


@dataclass(frozen=True, slots=True, kw_only=True)
class Placement:
    """One notatable part of a new rhythmic item, in the terms the create requests speak.

    ``measure`` and ``position`` name the anchor slot of its start; ``written_value`` is
    read in the units of ``scope`` — the voice, or the innermost group holding the item's
    start. Every part of one item shares that scope.
    """

    scope: RhythmicContainerParent
    measure: Measure
    position: MeasurePosition
    written_value: DottedRhythmicValue


@dataclass(frozen=True, slots=True, kw_only=True)
class Location:
    """Where a new rhythmic item sits before anything is cut or spelled: its scope, and
    its span written in that scope's own frame."""

    scope: RhythmicContainerParent
    span: Span


def locate(
    *,
    voice: Voice,
    measure: Measure,
    position: MeasurePosition,
    length: Fraction,
) -> Location:
    """The scope and span of an item of written ``length`` starting at ``position`` in
    ``measure``.

    The scope is the innermost one of ``voice`` holding the start (half-open: a start on
    a group's first instant is inside it); ``length`` is written in that scope's units.
    The item must fit in its scope, and a group and a voice are held to the same rule: an
    item may not tear out of its group, nor run past the last measure of its voice.
    """
    # a start outside its own measure is a wrong address, not a point further along: it
    # would silently land in the next measure, or off the end of the timeline
    if not measure.holds(position=position):
        raise MutationRejectedError("Position lies at or past the end of the measure.")

    geometry: ScoreGeometry = ScoreGeometry(origin=measure)
    start: Point = Point(
        frame=geometry.of_measure(measure=measure),
        value=position.value,
    ).to(frame=geometry.root)

    scope: RhythmicContainerParent
    local: Point
    scope, local = geometry.deepest_scope_at(point=start, voice=voice)
    span: Span = Span(frame=local.frame, start=local.value, length=length)

    # a group ends with its written interior, the timeline with the last measure
    if overflow(span=span) > 0:
        raise MutationRejectedError("Item does not fit in its scope.")

    return Location(scope=scope, span=span)


def place(
    *,
    voice: Voice,
    measure: Measure,
    position: MeasurePosition,
    length: Fraction,
) -> list[Placement]:
    """The parts of an item of written ``length`` starting at ``position`` in ``measure``.

    The item is located once (see ``locate``) — a part never re-derives its own scope,
    so a part beginning where a group begins still belongs to the item's scope. The fit
    is checked before the cut, so a barline on a group's end cannot hide a straddle.
    """
    location: Location = locate(
        voice=voice,
        measure=measure,
        position=position,
        length=length,
    )
    geometry: ScoreGeometry = ScoreGeometry(origin=measure)

    placements: list[Placement] = []

    for cut in geometry.slice_by_measures(span=location.span):
        # cut on the timeline, but written in the scope's own units
        written: Span = cut.part.to(frame=location.span.frame)

        try:
            mapped_sizes: list[DottedRhythmicValue] = _SIZE_MAPPER.spell_duration(
                duration=written.length
            )
        except ValueError as error:
            raise MutationRejectedError(f"Cannot spell a note part of {written.length}.") from error

        offset: Fraction = Fraction(0)
        for mapped in mapped_sizes:
            piece: Span = Span(
                frame=location.span.frame,
                start=written.start + offset,
                length=mapped.fraction,
            )
            at: Point = piece.start_point.to(frame=geometry.of_measure(measure=cut.region))

            placements.append(
                Placement(
                    scope=location.scope,
                    measure=cut.region,
                    position=MeasurePosition.of_fraction(fraction=at.value),
                    written_value=mapped,
                )
            )

            offset += mapped.fraction

    return placements
