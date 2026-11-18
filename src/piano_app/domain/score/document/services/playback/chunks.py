from collections.abc import Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import host_leaf_of, iter_leaves
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .anchors import PlayedAnchor, TimelineSegment, build_anchors
from .dynamics import Dynamics, build_dynamics
from .expansion import expand_sounds
from .loudness import PIANO_CURVE, DynamicCurve, velocities
from .pedal import PedalSpan, build_pedal
from .played import PlayedNote
from .projection import (
    Performance,
    PlaybackNote,
    PlaybackPedal,
    PlaybackProjection,
    perform,
    project_from,
    refuse_unplayable,
)
from .route import RouteSegment, build_route
from .sounds import Sound, build_rest_hosts, build_sounds
from .timeline import Timeline, build_timeline
from .timing import TimedNote, time_notes


@dataclass(frozen=True, slots=True, kw_only=True)
class Strike:
    """A note as a click plays it: alone, without ornaments, with the velocity of its voice
    where the score first plays its leaf, a mark of loudness included."""

    note_id: str
    pitch: int
    velocity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureSounds:
    """What one measure gives the playback: the strikes of its notes, the notes whose sound
    starts with one of its leaves and its leaves as they are played, in the times of the
    playback of the whole score."""

    measure_id: str
    strikes: tuple[Strike, ...]
    notes: tuple[PlaybackNote, ...]
    anchors: tuple[PlayedAnchor, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaybackChunks:
    """The playback of a score from its start cut by measure, in the order of the score, with
    what belongs to no one measure: its length, the pedal and the segments of the route."""

    measures: tuple[MeasureSounds, ...]
    extent_ms: float
    pedals: tuple[PlaybackPedal, ...]
    segments: tuple[TimelineSegment, ...]


def build_playback_chunks(
    *, document: ScoreDocument, curve: DynamicCurve = PIANO_CURVE
) -> PlaybackChunks:
    """The playback of the whole score cut by measure. A note, a leaf and a strike belong to
    the measure of the leaf they sound with: for a grace note the leaf of its group, for a
    tied chain the leaf of its first note. A note of a leaf the score never plays has no
    strike."""
    performance: Performance = perform(document=document, curve=curve)
    projection: PlaybackProjection = project_from(performance=performance, start=Fraction(0))
    leaves: list[LeafRhythmicContainer] = _leaves(document=document, measure_ids=None)

    return PlaybackChunks(
        measures=_lay_out(
            measure_ids=[measure.id for measure in document.measures],
            strikes=_strikes(
                leaves=leaves,
                sounds=performance.sounds,
                pitch=performance.pitch,
                dynamics=performance.dynamics,
                curve=curve,
            ),
            notes=_notes_from_start(timed=performance.timed, strengths=performance.strengths),
            anchors=_anchors_from_start(anchors=performance.anchors, leaves=leaves),
        ),
        extent_ms=projection.extent_ms,
        pedals=projection.pedals,
        segments=projection.segments,
    )


def build_measure_sounds(
    *,
    document: ScoreDocument,
    measure_ids: Collection[str],
    curve: DynamicCurve = PIANO_CURVE,
) -> tuple[MeasureSounds, ...]:
    """The share of the named measures in the playback of the whole score, as
    ``build_playback_chunks`` gives it, without playing the rest of the score: the tied chains
    that sound in them are read whole, the time, the pedal and the dynamics are those of the
    whole score, and only their own notes are played out. In the order of the score."""
    chosen: frozenset[str] = frozenset(measure_ids)
    leaves: list[LeafRhythmicContainer] = _leaves(document=document, measure_ids=chosen)

    # the leaves of every tied chain that sounds in the measures, so a chain is read as the
    # whole score reads it
    chained: set[str] = {leaf.id for leaf in leaves}
    pending: list[Note] = []
    for leaf in leaves:
        if isinstance(leaf.carrier, NoteCarrier):
            pending.extend(leaf.carrier.notes)
    seen: set[str] = {note.id for note in pending}
    while pending:
        note: Note = pending.pop()
        for relation in note.relations:
            if not isinstance(relation, Tie):
                continue

            for tied in (relation.start, relation.end):
                if tied.id in seen:
                    continue

                seen.add(tied.id)
                pending.append(tied)
                host: LeafRhythmicContainer | None = host_leaf_of(note=tied)
                if host is not None:
                    chained.add(host.id)

    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route: list[RouteSegment] = build_route(geometry=geometry, contexts=contexts)
    sounds: list[Sound] = build_sounds(
        document=document, geometry=geometry, route=route, leaf_ids=chained
    )
    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    played: list[PlayedNote] = []
    for played_note in expand_sounds(
        sounds=sounds,
        document=document,
        geometry=geometry,
        pitch=pitch,
        rests=build_rest_hosts(
            document=document, geometry=geometry, route=route, measure_ids=chosen
        ),
    ):
        if _measure_of(note=played_note.source) in chosen:
            played.append(played_note)
    refuse_unplayable(played=played)

    timeline: Timeline = build_timeline(route=route, geometry=geometry, contexts=contexts)
    pedal: list[PedalSpan] = build_pedal(route=route, geometry=geometry, contexts=contexts)
    dynamics: Dynamics = build_dynamics(
        document=document,
        route=route,
        geometry=geometry,
        contexts=contexts,
    )

    return _lay_out(
        measure_ids=[measure.id for measure in document.measures if measure.id in chosen],
        strikes=_strikes(leaves=leaves, sounds=sounds, pitch=pitch, dynamics=dynamics, curve=curve),
        notes=_notes_from_start(
            timed=time_notes(notes=played, timeline=timeline, pedal=pedal),
            strengths=velocities(notes=played, dynamics=dynamics, curve=curve),
        ),
        anchors=_anchors_from_start(
            anchors=build_anchors(
                document=document,
                geometry=geometry,
                route=route,
                timeline=timeline,
                measure_ids=chosen,
            ),
            leaves=leaves,
        ),
    )


def _leaves(
    *, document: ScoreDocument, measure_ids: Collection[str] | None
) -> list[LeafRhythmicContainer]:
    """The leaves of the score, voice by voice, or of the named measures only."""
    leaves: list[LeafRhythmicContainer] = []
    for voice in document.voices:
        for leaf in iter_leaves(voice):
            if measure_ids is None or leaf.anchor.measure.id in measure_ids:
                leaves.append(leaf)

    return leaves


def _measure_of(*, note: Note) -> str:
    """The measure of the leaf a note sounds with."""
    leaf: LeafRhythmicContainer | None = host_leaf_of(note=note)
    if leaf is None:
        raise ValueError(f"The note {note.id!r} does not stand in a metric leaf.")

    return leaf.anchor.measure.id


def _strikes(
    *,
    leaves: Sequence[LeafRhythmicContainer],
    sounds: Sequence[Sound],
    pitch: ScorePitch,
    dynamics: Dynamics,
    curve: DynamicCurve,
) -> list[tuple[str, Strike]]:
    """The strikes of the notes of the leaves, grace notes included, at the place the score
    first plays each leaf, with the measure of the leaf."""
    first_played: dict[str, Fraction] = {}
    for sound in sounds:
        for part in sound.parts:
            played_leaf: LeafRhythmicContainer | None = host_leaf_of(note=part.note)
            if played_leaf is not None and played_leaf.id not in first_played:
                first_played[played_leaf.id] = part.start

    struck: list[PlayedNote] = []
    homes: list[str] = []
    for leaf in leaves:
        if leaf.id not in first_played:
            continue

        held: list[Carrier | None] = [leaf.carrier]
        for grace_group in (leaf.grace_before, leaf.grace_after):
            if grace_group is not None:
                held.extend(item.carrier for item in grace_group.grace_items)

        for carrier in held:
            if not isinstance(carrier, NoteCarrier):
                continue

            for note in carrier.notes:
                struck.append(
                    PlayedNote(
                        source=note,
                        pitch=pitch.pitch_of(note=note).midi_note,
                        start=first_played[leaf.id],
                        end=first_played[leaf.id],
                    )
                )
                homes.append(leaf.anchor.measure.id)

    strikes: list[tuple[str, Strike]] = []
    for home, played, velocity in zip(
        homes, struck, velocities(notes=struck, dynamics=dynamics, curve=curve), strict=True
    ):
        strikes.append(
            (home, Strike(note_id=played.source.id, pitch=played.pitch, velocity=velocity))
        )

    return strikes


def _notes_from_start(
    *, timed: Sequence[TimedNote], strengths: Sequence[int]
) -> list[tuple[str, PlaybackNote]]:
    """The notes of the playback from the start of the score, as ``project_from`` gives them,
    each with the measure of the leaf it sounds with."""
    notes: list[tuple[str, PlaybackNote]] = []
    for note, velocity in zip(timed, strengths, strict=True):
        if note.end_ms > 0.0:
            notes.append(
                (
                    _measure_of(note=note.source),
                    PlaybackNote(
                        source_id=note.source.id,
                        pitch=note.pitch,
                        start_ms=max(note.start_ms, 0.0),
                        key_release_ms=max(note.key_release_ms, 0.0),
                        end_ms=note.end_ms,
                        velocity=velocity,
                    ),
                )
            )

    return notes


def _anchors_from_start(
    *, anchors: Sequence[PlayedAnchor], leaves: Sequence[LeafRhythmicContainer]
) -> list[tuple[str, PlayedAnchor]]:
    """The leaves as played from the start of the score, as ``project_from`` gives them, each
    with its measure."""
    measure_of_carrier: dict[str, str] = {}
    for leaf in leaves:
        if leaf.carrier is not None:
            measure_of_carrier[leaf.carrier.id] = leaf.anchor.measure.id

    played: list[tuple[str, PlayedAnchor]] = []
    for anchor in anchors:
        if anchor.end_ms > 0.0:
            played.append(
                (
                    measure_of_carrier[anchor.carrier_id],
                    PlayedAnchor(
                        carrier_id=anchor.carrier_id,
                        start_ms=max(anchor.start_ms, 0.0),
                        end_ms=anchor.end_ms,
                    ),
                )
            )

    return played


def _lay_out(
    *,
    measure_ids: Sequence[str],
    strikes: Sequence[tuple[str, Strike]],
    notes: Sequence[tuple[str, PlaybackNote]],
    anchors: Sequence[tuple[str, PlayedAnchor]],
) -> tuple[MeasureSounds, ...]:
    """The strikes, notes and leaves laid out in the named measures, in that order."""
    strikes_of: dict[str, list[Strike]] = {measure_id: [] for measure_id in measure_ids}
    for home, strike in strikes:
        strikes_of[home].append(strike)

    notes_of: dict[str, list[PlaybackNote]] = {measure_id: [] for measure_id in measure_ids}
    for home, note in notes:
        notes_of[home].append(note)

    anchors_of: dict[str, list[PlayedAnchor]] = {measure_id: [] for measure_id in measure_ids}
    for home, anchor in anchors:
        anchors_of[home].append(anchor)

    measures: list[MeasureSounds] = []
    for measure_id in measure_ids:
        measures.append(
            MeasureSounds(
                measure_id=measure_id,
                strikes=tuple(strikes_of[measure_id]),
                notes=tuple(notes_of[measure_id]),
                anchors=tuple(anchors_of[measure_id]),
            )
        )

    return tuple(measures)
