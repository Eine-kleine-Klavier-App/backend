from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.material import (
    Carrier,
    Note,
    NoteCarrier,
    RestCarrier,
)
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import voice_of

from .index import ContextIndex
from .scope import Scope, scopes_of


@dataclass(frozen=True, slots=True, kw_only=True)
class Coverage:
    """What a context is applied to: the carriers and the notes, in the order of the timeline."""

    carriers: tuple[Carrier, ...]
    notes: tuple[Note, ...]


def covered_by(
    *,
    context: Context,
    document: ScoreDocument,
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> Coverage:
    """The elements ``context`` is applied to: those that start inside its region ``[start, end)``
    and belong to what it governs. One rule for every kind of context.

    A span context governs its region in each of its scopes. A point context governs, in each of
    its scopes, from its place until the next context of its kind there. The scope says which
    elements belong: the whole score takes all of them, a voice its own carriers, a staff the
    notes and rests that stand on it.
    """
    start: Fraction = geometry.point_of(anchor=context.start).value
    regions: list[tuple[Scope, Fraction, Fraction]] = []
    for scope in scopes_of(context=context):
        if isinstance(context, SpanContext):
            end: Fraction = geometry.end_of(context=context).value
        else:
            end = contexts.piece_at(kind=type(context), point=start, scope=scope).span.end

        regions.append((scope, start, end))

    carriers: dict[str, Carrier] = {}
    notes: dict[str, Note] = {}
    for measure in document.measures:
        for anchor in measure.anchors:
            onset: Fraction = geometry.point_of(anchor=anchor).value
            for container in anchor.containers:
                if not isinstance(container, LeafRhythmicContainer) or container.carrier is None:
                    continue

                carrier: Carrier = container.carrier
                voice: Voice = voice_of(container)
                for scope, region_start, region_end in regions:
                    if not region_start <= onset < region_end:
                        continue

                    held: list[Note] = _held_by(carrier=carrier, scope=scope, voice=voice)
                    if held or (
                        isinstance(carrier, RestCarrier)
                        and _rest_is_held(carrier=carrier, scope=scope, voice=voice)
                    ):
                        carriers[carrier.id] = carrier
                        for note in held:
                            notes[note.id] = note

    return Coverage(carriers=tuple(carriers.values()), notes=tuple(notes.values()))


def _held_by(*, carrier: Carrier, scope: Scope, voice: Voice) -> list[Note]:
    """The notes of a note carrier that belong to ``scope``: all of them in the whole score or in
    their voice, those on the staff in a staff."""
    if not isinstance(carrier, NoteCarrier):
        return []

    if scope.voice is not None:
        return list(carrier.notes) if scope.voice is voice else []

    if scope.staff is not None:
        return [note for note in carrier.notes if note.staff is scope.staff]

    return list(carrier.notes)


def _rest_is_held(*, carrier: RestCarrier, scope: Scope, voice: Voice) -> bool:
    """Whether a rest belongs to ``scope``: in the whole score, in its voice, on its staff."""
    if scope.voice is not None:
        return scope.voice is voice

    if scope.staff is not None:
        return carrier.rest is not None and carrier.rest.staff is scope.staff

    return True
