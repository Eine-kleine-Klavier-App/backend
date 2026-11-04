from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves

from .route import RouteSegment


@dataclass(frozen=True, slots=True, kw_only=True)
class SoundPart:
    """One note of a sound with the stretch of time its leaf is played in."""

    note: Note
    start: Fraction
    end: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class Sound:
    """One attack of a note and everything that is tied on to it: its notes in order, each
    with its own stretch, in the time of the route, which is the time of the score as it is
    played, in whole notes (the length of the route's stretches added up)."""

    parts: tuple[SoundPart, ...]

    @property
    def notes(self) -> tuple[Note, ...]:
        return tuple(part.note for part in self.parts)

    @property
    def start(self) -> Fraction:
        return self.parts[0].start

    @property
    def end(self) -> Fraction:
        return self.parts[-1].end


@dataclass(frozen=True, slots=True, kw_only=True)
class RestHost:
    """A rest that holds grace notes, with the stretch of time its leaf is played in: a rest
    makes no sound of its own, the grace notes on it sound inside that stretch."""

    leaf: LeafRhythmicContainer
    start: Fraction
    end: Fraction


def build_sounds(
    *,
    document: ScoreDocument,
    geometry: ScoreGeometry,
    route: Sequence[RouteSegment],
) -> list[Sound]:
    """The sounds of the metric notes of a score, in the order they are played.

    Every stretch of the route is read in turn, so a note in a repeated part sounds once for
    each pass, and each pass is read by itself. A leaf belongs to the stretch it starts in and
    is cut at the end of it. A note continues the sound of the note tied to it only if that
    note was played right before it in the same stretch; after a jump it sounds again. Rests
    and grace notes make no sound here.
    """
    sounds: list[Sound] = []
    offset: Fraction = Fraction(0)
    for segment in route:
        # the last note of each tied chain played so far in this stretch, and where its sound is
        open_chains: dict[Note, int] = {}
        for voice in document.voices:
            _read_voice(
                voice=voice,
                geometry=geometry,
                segment=segment,
                offset=offset,
                sounds=sounds,
                open_chains=open_chains,
            )

        offset += segment.end - segment.start

    sounds.sort(key=lambda sound: sound.start)

    return sounds


def _read_voice(
    *,
    voice: Voice,
    geometry: ScoreGeometry,
    segment: RouteSegment,
    offset: Fraction,
    sounds: list[Sound],
    open_chains: dict[Note, int],
) -> None:
    leaf: LeafRhythmicContainer
    for leaf in iter_leaves(voice):
        carrier: Carrier | None = leaf.carrier
        if not isinstance(carrier, NoteCarrier):
            continue

        span: Span = geometry.global_span_of(container=leaf)
        if not segment.start <= span.start < segment.end:
            continue

        start: Fraction = offset + span.start - segment.start
        end: Fraction = offset + min(span.end, segment.end) - segment.start
        for note in carrier.notes:
            tie_in: Tie | None = None
            tie_out: Tie | None = None
            for relation in note.relations:
                if not isinstance(relation, Tie):
                    continue

                if relation.end is note:
                    tie_in = relation
                else:
                    tie_out = relation

            index: int | None = None
            if tie_in is not None:
                index = open_chains.pop(tie_in.start, None)

            part: SoundPart = SoundPart(note=note, start=start, end=end)
            if index is None:
                index = len(sounds)
                sounds.append(Sound(parts=(part,)))
            else:
                sounds[index] = Sound(parts=(*sounds[index].parts, part))

            if tie_out is not None:
                open_chains[note] = index


def build_rest_hosts(
    *,
    document: ScoreDocument,
    geometry: ScoreGeometry,
    route: Sequence[RouteSegment],
) -> list[RestHost]:
    """The rests that hold grace notes, in the order they are played, read stretch by stretch
    like the sounds are: a rest in a repeated part is a host once for each pass."""
    hosts: list[RestHost] = []
    offset: Fraction = Fraction(0)
    for segment in route:
        for voice in document.voices:
            leaf: LeafRhythmicContainer
            for leaf in iter_leaves(voice):
                if not isinstance(leaf.carrier, RestCarrier):
                    continue

                if leaf.grace_before is None and leaf.grace_after is None:
                    continue

                span: Span = geometry.global_span_of(container=leaf)
                if not segment.start <= span.start < segment.end:
                    continue

                hosts.append(
                    RestHost(
                        leaf=leaf,
                        start=offset + span.start - segment.start,
                        end=offset + min(span.end, segment.end) - segment.start,
                    )
                )

        offset += segment.end - segment.start

    hosts.sort(key=lambda host: host.start)

    return hosts
