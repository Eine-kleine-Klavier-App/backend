from bisect import bisect_right
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import host_leaf_of
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .anchors import (
    Moment,
    PlayedAnchor,
    TimelineSegment,
    build_anchors,
    build_segments,
)
from .dynamics import Dynamics, build_dynamics
from .expansion import expand_sounds
from .loudness import PIANO_CURVE, DynamicCurve, velocities
from .pedal import PedalSpan, build_pedal
from .played import PlayedNote
from .route import RouteSegment, build_route
from .sounds import Sound, build_rest_hosts, build_sounds
from .timeline import Timeline, build_timeline
from .timing import TimedNote, time_notes


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackNote:
    """A note to be played: the id of the note it comes from (the main note for an ornament
    or an arpeggio, the grace note itself for a grace note), its MIDI number, attack,
    physical key release and end of sustain holding in playback milliseconds. The acoustic
    release tail depends on the instrument. Attack velocity is 1 to 127."""

    source_id: str
    pitch: int
    start_ms: float
    key_release_ms: float
    end_ms: float
    velocity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackPedal:
    """One sustain-pedal press and release in playback milliseconds."""

    down_ms: float
    up_ms: float


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackProjection:
    """What sounds, by the time it starts, and how long the playback lasts, with the leaves as
    they are played and the segments that tell the time of a place of the score."""

    notes: tuple[PlaybackNote, ...]
    extent_ms: float
    anchors: tuple[PlayedAnchor, ...] = ()
    segments: tuple[TimelineSegment, ...] = ()
    pedals: tuple[PlaybackPedal, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class Performance:
    """The score played once from its start, with what each step of the playing found: the
    playback from a place and the playback cut by measure both read it, so a score is played
    once for either."""

    geometry: ScoreGeometry
    contexts: ContextIndex
    route: list[RouteSegment]
    sounds: list[Sound]
    pitch: ScorePitch
    dynamics: Dynamics
    timeline: Timeline
    pedal: list[PedalSpan]
    timed: list[TimedNote]
    strengths: list[int]
    anchors: list[PlayedAnchor]
    segments: list[TimelineSegment]


def refuse_unplayable(*, played: Sequence[PlayedNote]) -> None:
    """Refuse a note that would sound outside MIDI 0..127, naming it."""
    for sound in played:
        if not 0 <= sound.pitch <= 127:
            raise ValueError(
                f"The note {sound.source.id!r} sounds at {sound.pitch}, outside MIDI 0..127."
            )


def perform(*, document: ScoreDocument, curve: DynamicCurve = PIANO_CURVE) -> Performance:
    """The score played from its start in the order its repeats give. A note that would sound
    outside MIDI 0..127 is refused. The document is only read."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route: list[RouteSegment] = build_route(geometry=geometry, contexts=contexts)
    sounds: list[Sound] = build_sounds(document=document, geometry=geometry, route=route)
    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    played: list[PlayedNote] = expand_sounds(
        sounds=sounds,
        document=document,
        geometry=geometry,
        pitch=pitch,
        rests=build_rest_hosts(document=document, geometry=geometry, route=route),
    )
    refuse_unplayable(played=played)

    timeline: Timeline = build_timeline(route=route, geometry=geometry, contexts=contexts)
    pedal: list[PedalSpan] = build_pedal(route=route, geometry=geometry, contexts=contexts)
    dynamics: Dynamics = build_dynamics(
        document=document,
        route=route,
        geometry=geometry,
        contexts=contexts,
    )

    return Performance(
        geometry=geometry,
        contexts=contexts,
        route=route,
        sounds=sounds,
        pitch=pitch,
        dynamics=dynamics,
        timeline=timeline,
        pedal=pedal,
        timed=time_notes(notes=played, timeline=timeline, pedal=pedal),
        strengths=velocities(notes=played, dynamics=dynamics, curve=curve),
        anchors=build_anchors(document=document, geometry=geometry, route=route, timeline=timeline),
        segments=build_segments(
            document=document, geometry=geometry, route=route, timeline=timeline
        ),
    )


def build_projection(
    *,
    document: ScoreDocument,
    curve: DynamicCurve = PIANO_CURVE,
    start: Fraction = Fraction(0),
) -> PlaybackProjection:
    """The playback of a score from ``start``, a position of the score in whole notes.

    The score is played in the order its repeats give, and ``start`` is the place where that
    order first passes it, with the tempo and the dynamics it has carried there. A note that
    sounds through the start is struck again from there with its own velocity and what is
    left of its length. The end of the score is a start with nothing to play; a position
    outside the score, or one that is never played, is refused. The document is only read.
    """
    return project_from(performance=perform(document=document, curve=curve), start=start)


def project_from(*, performance: Performance, start: Fraction) -> PlaybackProjection:
    """The playback of a performed score from ``start``, as ``build_projection`` tells it."""
    geometry: ScoreGeometry = performance.geometry
    route: list[RouteSegment] = performance.route
    timeline: Timeline = performance.timeline
    pedal: list[PedalSpan] = performance.pedal
    timed: list[TimedNote] = performance.timed
    strengths: list[int] = performance.strengths
    anchors: list[PlayedAnchor] = performance.anchors
    segments: list[TimelineSegment] = performance.segments

    if not 0 <= start <= geometry.root.extent:
        raise ValueError("The start lies outside the score.")

    from_ms: float = 0.0
    if start == geometry.root.extent:
        return PlaybackProjection(notes=(), extent_ms=0.0)

    if start > 0:
        offset: Fraction = Fraction(0)
        for segment in route:
            if segment.start <= start < segment.end:
                from_ms = timeline.ms_at(position=offset + start - segment.start)
                break

            offset += segment.end - segment.start
        else:
            raise ValueError("The start lies in a part of the score that is never played.")

    notes: list[PlaybackNote] = []
    for note, velocity in zip(timed, strengths, strict=True):
        if note.end_ms > from_ms:
            notes.append(
                PlaybackNote(
                    source_id=note.source.id,
                    pitch=note.pitch,
                    start_ms=max(note.start_ms, from_ms) - from_ms,
                    key_release_ms=max(note.key_release_ms, from_ms) - from_ms,
                    end_ms=note.end_ms - from_ms,
                    velocity=velocity,
                )
            )

    cut_anchors: list[PlayedAnchor] = []
    for anchor in anchors:
        if anchor.end_ms > from_ms:
            cut_anchors.append(
                PlayedAnchor(
                    carrier_id=anchor.carrier_id,
                    start_ms=max(anchor.start_ms, from_ms) - from_ms,
                    end_ms=anchor.end_ms - from_ms,
                )
            )

    cut_segments: list[TimelineSegment] = []
    for mapped in segments:
        if mapped.end_ms <= from_ms:
            continue

        moments: list[Moment] = []
        first: Fraction = mapped.start
        if mapped.start_ms < from_ms:
            # the start falls inside the segment: its place is found between the moments around
            index: int = bisect_right([moment.time_ms for moment in mapped.moments], from_ms)
            before: Moment = mapped.moments[index - 1]
            after: Moment = mapped.moments[index]
            share: Fraction = Fraction(
                (from_ms - before.time_ms) / (after.time_ms - before.time_ms)
            ).limit_denominator(1_000_000)
            first = before.position + (after.position - before.position) * share
            moments.append(Moment(position=first, time_ms=0.0))
            moments.extend(
                Moment(position=moment.position, time_ms=moment.time_ms - from_ms)
                for moment in mapped.moments[index:]
            )
        else:
            moments.extend(
                Moment(position=moment.position, time_ms=moment.time_ms - from_ms)
                for moment in mapped.moments
            )

        cut_segments.append(
            TimelineSegment(
                start=first,
                end=mapped.end,
                start_ms=moments[0].time_ms,
                end_ms=mapped.end_ms - from_ms,
                moments=tuple(moments),
            )
        )

    return PlaybackProjection(
        notes=tuple(notes),
        extent_ms=timeline.ms_at(position=timeline.extent) - from_ms,
        anchors=tuple(cut_anchors),
        segments=tuple(cut_segments),
        pedals=tuple(
            PlaybackPedal(
                down_ms=max(timeline.ms_at(position=span.start), from_ms) - from_ms,
                up_ms=timeline.ms_at(position=span.end) - from_ms,
            )
            for span in pedal
            if timeline.ms_at(position=span.end) > from_ms
        ),
    )


def preview_chord(
    *,
    document: ScoreDocument,
    carrier: NoteCarrier,
    note_ids: Collection[str] | None = None,
    curve: DynamicCurve = PIANO_CURVE,
    duration_ms: float = 650.0,
) -> PlaybackProjection:
    """The chord of a carrier, or the notes of it that ``note_ids`` names, struck together for
    ``duration_ms``, without ornaments: to hear what a note is. The velocity is that of the
    dynamic of its voice where the score first plays the leaf, a mark of loudness included."""
    chosen: list[Note] = list(carrier.notes)
    if note_ids is not None:
        wanted: set[str] = set(note_ids)
        if not wanted:
            raise ValueError("Name at least one note.")

        chosen = [note for note in carrier.notes if note.id in wanted]
        if len(chosen) != len(wanted):
            raise ValueError("The notes do not belong to the carrier.")

    leaf: LeafRhythmicContainer | None = host_leaf_of(note=chosen[0])
    if leaf is None:
        raise ValueError("The carrier does not stand in a metric leaf.")

    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route: list[RouteSegment] = build_route(geometry=geometry, contexts=contexts)
    sounds: list[Sound] = build_sounds(document=document, geometry=geometry, route=route)
    position: Fraction | None = None
    for sound in sounds:
        for part in sound.parts:
            if host_leaf_of(note=part.note) is leaf:
                position = part.start
                break

        if position is not None:
            break

    if position is None:
        raise ValueError("The carrier is never played.")

    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    struck: list[PlayedNote] = []
    for note in chosen:
        struck.append(
            PlayedNote(
                source=note,
                pitch=pitch.pitch_of(note=note).midi_note,
                start=position,
                end=position,
            )
        )

    strengths: list[int] = velocities(
        notes=struck,
        dynamics=build_dynamics(
            document=document,
            route=route,
            geometry=geometry,
            contexts=contexts,
        ),
        curve=curve,
    )

    return PlaybackProjection(
        notes=tuple(
            PlaybackNote(
                source_id=played.source.id,
                pitch=played.pitch,
                start_ms=0.0,
                key_release_ms=duration_ms,
                end_ms=duration_ms,
                velocity=velocity,
            )
            for played, velocity in zip(struck, strengths, strict=True)
        ),
        extent_ms=duration_ms,
    )
