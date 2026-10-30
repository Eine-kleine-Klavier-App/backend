from dataclasses import dataclass, replace

from piano_app.domain.score.document.models.material import (
    Carrier,
    Note,
    NoteCarrier,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.content import (
    create_note,
    create_piece,
    tie_pieces,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.free import (
    free_room,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.pieces import (
    Piece,
    cut_into_pieces,
    point_of_piece,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.room import (
    locate_item,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    NoteContent,
    PlaceSpansRequest,
    RestContent,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


@dataclass(frozen=True, slots=True, kw_only=True)
class _Landing:
    """A piece of the item and what it meets.

    ``met`` are the containers of the item's scope the piece reaches into; ``joined`` is
    the carrier of the one note leaf it lands on exactly, span for span, if that is all it
    meets.
    """

    piece: Piece
    met: list[RhythmicContainer]
    joined: NoteCarrier | None


class PlaceSpansAnalyzer:
    """Places a new rhythmic item: its scope, its pieces, and what happens to the spans
    it meets.

    The scope is the deepest one holding the start on the live document, and the item
    must fit there (refused otherwise); it is cut at the barlines and each cut is spelled
    in the scope's units. When the item is a note and every piece lands exactly on a note
    leaf of its span, the new notes join those chords and nothing is removed. Otherwise
    every container the item meets — a leaf, or a group with everything in it — is
    removed. Each piece is created as a new leaf with its carrier and its note or rest,
    then the new notes are tied piece to piece; rests are not.

    Everything geometric is decided before the first yield; only model terms (measures,
    positions, values) and the met entities are carried across.
    """

    def analyze(
        self,
        *,
        request: PlaceSpansRequest,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis:
        scope: RhythmicContainerParent
        span: Span
        scope, span = locate_item(
            geometry=geometry,
            voice=request.voice,
            measure=request.measure,
            position=request.position,
            written_length=request.written_length,
        )

        landings: list[_Landing] = []
        for piece in cut_into_pieces(geometry=geometry, span=span):
            met: list[RhythmicContainer] = [
                meeting.region for meeting in geometry.intersecting(span=piece.span, scope=scope)
            ]

            joined: NoteCarrier | None = None
            if len(met) == 1 and isinstance(met[0], LeafRhythmicContainer):
                met_span: Span = geometry.span_of(container=met[0])
                carrier: Carrier | None = met[0].carrier
                if (
                    isinstance(carrier, NoteCarrier)
                    and met_span.start == piece.span.start
                    and met_span.length == piece.span.length
                ):
                    joined = carrier

            landings.append(_Landing(piece=piece, met=met, joined=joined))

        content: NoteContent | RestContent = request.content
        joined_carriers: list[NoteCarrier] = [
            landing.joined for landing in landings if landing.joined is not None
        ]
        notes: list[Note] = []

        # an item always has a piece; with none, every piece joining would hold vacuously
        if not landings:
            raise ValueError("A placed item must have at least one piece.")

        # the pieces of a note sound as one: each stands on the step that sounds as the first
        # does where it lies, which another clef or octave line there may make another step
        note_contents: list[NoteContent] = []
        if isinstance(content, NoteContent):
            try:
                first_pitch: int = pitch.resolve(
                    staff=content.staff,
                    point=point_of_piece(geometry=geometry, piece=landings[0].piece),
                    staff_step=content.staff_step,
                    accidental=content.accidental,
                ).midi_note
                note_contents = [
                    content
                    if index == 0
                    else replace(
                        content,
                        staff_step=pitch.staff_step_for(
                            staff=content.staff,
                            point=point_of_piece(geometry=geometry, piece=landing.piece),
                            midi_note=first_pitch,
                            accidental=content.accidental,
                        ),
                    )
                    for index, landing in enumerate(landings)
                ]
            except PitchResolutionError as error:
                raise MutationRejectedError(
                    "A note is placed where no clef is in force."
                ) from error

        if isinstance(content, NoteContent) and len(joined_carriers) == len(landings):
            # every piece lands on a note of its own span: a chord, nothing is removed
            for joined_carrier, note_content in zip(joined_carriers, note_contents, strict=True):
                notes.append((yield from create_note(carrier=joined_carrier, note=note_content)))

        else:
            # anything else met — a rest, a note of another span, several elements, or
            # nothing for one of the pieces — means no join: every element met goes
            met_all: list[RhythmicContainer] = []
            for landing in landings:
                met_all.extend(landing.met)

            yield from free_room(met=met_all)

            for index, landing in enumerate(landings):
                _leaf, piece_notes = yield from create_piece(
                    scope=scope,
                    piece=landing.piece,
                    content=[note_contents[index]] if isinstance(content, NoteContent) else content,
                )
                notes.extend(piece_notes)

        # the pieces of a note sound as one: each is tied to the next, after all exist
        yield from tie_pieces(notes_by_piece=[[note] for note in notes])
