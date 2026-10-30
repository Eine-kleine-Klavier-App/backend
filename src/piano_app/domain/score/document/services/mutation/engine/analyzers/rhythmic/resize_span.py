from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Articulation,
    DottedRhythmicValue,
    GracePlacement,
    Ornament,
    RhythmicSize,
)
from piano_app.domain.score.document.models.relations.start_end import NoteToNoteRelation
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Point, Span, overflow
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
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
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateRestCarrierRequest,
    CreateRestRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    UpdateRelationStartRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateGraceGroupRequest,
    CreateGraceItemRequest,
    NoteContent,
    ResizeSpanRequest,
    RestContent,
    UpdateLeafSizeRequest,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class ResizeSpanAnalyzer:
    """Gives an existing leaf a new span from where it starts, and decides what happens
    to the spans it meets.

    The new span must fit the leaf's scope (refused otherwise); it is cut at the barlines
    and each cut is spelled in the scope's units. Every other container of the scope it
    meets — a leaf, or a group with everything in it — is removed. The first piece is the
    same leaf resized in place — its carrier, notes, stem override and ids stay, and an
    unchanged size writes nothing; every further piece is a new leaf with the content
    copied, its notes tied piece to piece (rests are not). A shorter span leaves its freed
    room to fill. The element's relations stay on the first piece, except that when the
    span is cut each tie and glissando starting at one of its notes moves to the same note
    of the last piece, keeping its identity. The grace notes before the note stay with the
    first piece; the ones after it go to the last piece, made again there with the same kind,
    values and sounds (each on the step that sounds the same there), and refused if that piece
    cannot give them the time.

    Everything geometric is decided before the first yield; only model terms (measures,
    positions, values) and entities are carried across.
    """

    def analyze(
        self,
        *,
        request: ResizeSpanRequest,
        geometry: ScoreGeometry,
        pitch: ScorePitch,
    ) -> MutationAnalysis:
        leaf: LeafRhythmicContainer = request.leaf
        scope: RhythmicContainerParent = leaf.parent

        room: Span = geometry.span_of(container=leaf)
        span: Span = Span(
            frame=room.frame,
            start=room.start,
            length=request.written_value.fraction,
        )

        # a group ends with its written interior, the timeline with the last measure
        if overflow(span=span) > 0:
            raise MutationRejectedError("The resized element does not fit in its scope.")

        pieces: list[Piece] = cut_into_pieces(geometry=geometry, span=span)
        if not pieces:
            raise ValueError("A resized span must have at least one piece.")

        met: list[RhythmicContainer] = []
        for meeting in geometry.intersecting(span=span, scope=scope):
            if meeting.region is not leaf:
                met.append(meeting.region)

        carrier: Carrier | None = leaf.carrier
        notes: list[Note] = []
        rest_staff: Staff | None = None
        if isinstance(carrier, NoteCarrier):
            notes = list(carrier.notes)
        elif isinstance(carrier, RestCarrier):
            rest: Rest | None = carrier.rest
            if rest is None:
                raise ValueError("A resized rest carrier must hold its rest.")

            rest_staff = rest.staff
        else:
            raise ValueError("A resized leaf must hold a note or a rest carrier.")

        # the pieces of a note sound as one: each later piece stands on the step that sounds as
        # the note does, which another clef or octave line where the piece lies may make
        # another step
        steps_by_piece: list[list[int]] = []
        for piece in pieces[1:]:
            point: Point = point_of_piece(geometry=geometry, piece=piece)
            try:
                steps_by_piece.append(
                    [
                        pitch.staff_step_for(
                            staff=note.staff,
                            point=point,
                            midi_note=pitch.pitch_of(note=note).midi_note,
                            accidental=note.accidental,
                        )
                        for note in notes
                    ]
                )
            except PitchResolutionError as error:
                raise MutationRejectedError("A note is cut where no clef is in force.") from error

        # each relation starting at a note of a cut element moves to the same note of the
        # last piece, so the first piece's notes are free to tie on to the next piece; one
        # ending in a met leaf, or in a leaf inside a met group, goes with it first
        moving: list[tuple[int, NoteToNoteRelation]] = []
        if len(pieces) > 1:
            for index, note in enumerate(notes):
                for relation in note.relations:
                    if relation.start is not note:
                        continue

                    partner: CarrierOwner = relation.end.note_carrier.owner
                    holder: RhythmicContainerParent | RhythmicContainer | None = (
                        partner if isinstance(partner, RhythmicContainer) else None
                    )
                    goes: bool = False
                    while not goes and isinstance(holder, RhythmicContainer):
                        goes = any(holder is container for container in met)
                        holder = holder.parent

                    if not goes:
                        moving.append((index, relation))

        # the grace notes after a cut note are read off before they go, so that the first piece
        # has its time back when it is resized
        after: GraceGroup | None = leaf.grace_after if len(pieces) > 1 else None
        moved: list[
            tuple[
                DottedRhythmicValue,
                frozenset[Articulation],
                Ornament,
                list[NoteContent] | RestContent,
            ]
        ] = []
        if after is not None:
            last_point: Point = point_of_piece(geometry=geometry, piece=pieces[-1])
            for grace in after.grace_items:
                grace_carrier: Carrier | None = grace.carrier
                if isinstance(grace_carrier, RestCarrier) and grace_carrier.rest is not None:
                    moved.append(
                        (
                            grace.rhythmic_value,
                            frozenset(),
                            Ornament.NONE,
                            RestContent(staff=grace_carrier.rest.staff),
                        )
                    )
                    continue

                if not isinstance(grace_carrier, NoteCarrier):
                    raise MutationRejectedError(
                        "Grace notes after a note that is cut are moved with their notes only."
                    )

                moved.append(
                    (
                        grace.rhythmic_value,
                        grace_carrier.articulations,
                        grace_carrier.ornament,
                        [
                            NoteContent(
                                staff=grace_note.staff,
                                staff_step=pitch.staff_step_for(
                                    staff=grace_note.staff,
                                    point=last_point,
                                    midi_note=pitch.pitch_of(note=grace_note).midi_note,
                                    accidental=grace_note.accidental,
                                ),
                                accidental=grace_note.accidental,
                                fingering=grace_note.fingering,
                            )
                            for grace_note in grace_carrier.notes
                        ],
                    )
                )

        yield from free_room(met=met)

        if after is not None:
            yield DeleteRequest(target=after)

        first_size: RhythmicSize = RhythmicSize(value=pieces[0].written_value, count=1)
        if leaf.written_size != first_size:
            yield UpdateLeafSizeRequest(target=leaf, written_size=first_size)

        notes_by_piece: list[list[Note]] = [notes]
        last_leaf: LeafRhythmicContainer = leaf
        for piece_index, piece in enumerate(pieces[1:]):
            if isinstance(carrier, NoteCarrier):
                last_leaf, piece_notes = yield from create_piece(
                    scope=scope,
                    piece=piece,
                    content=[
                        NoteContent(
                            staff=note.staff,
                            staff_step=steps_by_piece[piece_index][note_index],
                            accidental=note.accidental,
                            fingering=note.fingering,
                        )
                        for note_index, note in enumerate(notes)
                    ],
                    articulations=carrier.articulations,
                    ornament=carrier.ornament,
                )
                notes_by_piece.append(piece_notes)
            elif rest_staff is not None:
                last_leaf, _no_notes = yield from create_piece(
                    scope=scope,
                    piece=piece,
                    content=RestContent(staff=rest_staff),
                )

        if after is not None:
            last_group: GraceGroup = expect_sent(
                sent=(
                    yield CreateGraceGroupRequest(
                        leaf=last_leaf,
                        grace_type=after.grace_type,
                        placement=GracePlacement.AFTER,
                    )
                ),
                expected=GraceGroup,
            )
            for value, articulations, ornament, contents in moved:
                grace_item: GraceItem = expect_sent(
                    sent=(yield CreateGraceItemRequest(group=last_group, rhythmic_value=value)),
                    expected=GraceItem,
                )
                if isinstance(contents, RestContent):
                    grace_rest_carrier: RestCarrier = expect_sent(
                        sent=(yield CreateRestCarrierRequest(owner=grace_item)),
                        expected=RestCarrier,
                    )
                    yield CreateRestRequest(carrier=grace_rest_carrier, staff=contents.staff)
                    continue

                grace_carrier_new: NoteCarrier = expect_sent(
                    sent=(
                        yield CreateNoteCarrierRequest(
                            owner=grace_item, articulations=articulations, ornament=ornament
                        )
                    ),
                    expected=NoteCarrier,
                )
                for content in contents:
                    yield from create_note(carrier=grace_carrier_new, note=content)

        for index, relation in moving:
            yield UpdateRelationStartRequest(target=relation, start_note=notes_by_piece[-1][index])

        # each note of a piece is tied to its counterpart in the next, after all exist
        yield from tie_pieces(notes_by_piece=notes_by_piece)
