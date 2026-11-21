from fractions import Fraction

import pytest

from piano_app.adapters.outbound.importers.musicxml.reader import MusicXmlReader
from piano_app.application.ports.importing import ImportIssue, ImportRefusedError, IssueKind
from piano_app.application.use_cases.score.import_score.builder import BuiltScore, ScoreBuilder
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    Context,
    DynamicChange,
    Hairpin,
    OctaveTransposition,
    Refrain,
    Slur,
    SustainHold,
    TempoChange,
    Volta,
)
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    Clef,
    DynamicMarking,
    Fingering,
    Ornament,
)
from piano_app.domain.score.document.models.notation.stem import StemDirection
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

_SOUND: dict[str, int] = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _note(
    step: str,
    octave: int,
    *,
    duration: int = 2,
    kind: str = "quarter",
    alter: int = 0,
    voice: int = 1,
    staff: int = 1,
    chord: bool = False,
    extra: str = "",
) -> str:
    sign: str = f"<alter>{alter}</alter>" if alter else ""
    return (
        f"<note>{'<chord/>' if chord else ''}<pitch><step>{step}</step>{sign}"
        f"<octave>{octave}</octave></pitch><duration>{duration}</duration><voice>{voice}</voice>"
        f"<type>{kind}</type><staff>{staff}</staff>{extra}</note>"
    )


def _rest(*, duration: int = 2, kind: str = "quarter", voice: int = 1, staff: int = 1) -> str:
    return (
        f"<note><rest/><duration>{duration}</duration><voice>{voice}</voice>"
        f"<type>{kind}</type><staff>{staff}</staff></note>"
    )


def _attributes(
    *, beats: int = 3, beat_type: int = 4, fifths: int = 0, extra: str = "", divisions: int = 2
) -> str:
    return (
        f"<attributes><divisions>{divisions}</divisions><key><fifths>{fifths}</fifths></key>"
        f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time><staves>2</staves>"
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        f'<clef number="2"><sign>F</sign><line>4</line></clef>{extra}</attributes>'
    )


def _measure(number: int, *, body: str, attributes: str = "", implicit: bool = False) -> str:
    mark: str = ' implicit="yes"' if implicit else ""
    return f'<measure number="{number}"{mark}>{attributes}{body}</measure>'


def _build(*measures: str) -> BuiltScore:
    xml: bytes = (
        "<score-partwise><part-list/><part id='P1'>"
        + "".join(measures)
        + "</part></score-partwise>"
    ).encode()

    return ScoreBuilder(engine=build_engine(), compiler=build_compiler()).build(
        source=MusicXmlReader().read(data=xml)
    )


def _sounding(document: ScoreDocument) -> list[tuple[int, Fraction, int, int, int]]:
    """Every note as (measure, position in whole notes, voice, staff, MIDI number), in order."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    found: list[tuple[int, Fraction, int, int, int]] = []
    for voice_index, voice in enumerate(document.voices):
        for leaf in _leaves(voice.children):
            if not isinstance(leaf.carrier, NoteCarrier):
                continue

            for note in leaf.carrier.notes:
                found.append(
                    (
                        document.measures.index(leaf.anchor.measure),
                        leaf.anchor.position.value,
                        voice_index,
                        document.staffs.index(note.staff),
                        pitch.pitch_of(note=note).midi_note,
                    )
                )

    return sorted(found, key=lambda item: (item[0], item[1], item[2], item[4]))


def _ties(document: ScoreDocument) -> list[tuple[tuple[int, Fraction], tuple[int, Fraction]]]:
    """Every tie as ((measure, position) of its first note, (measure, position) of its last)."""
    places: dict[object, tuple[int, Fraction]] = {}
    ties: list[Tie] = []
    for voice in document.voices:
        for leaf in _leaves(voice.children):
            if isinstance(leaf.carrier, NoteCarrier):
                for note in leaf.carrier.notes:
                    places[note] = (
                        document.measures.index(leaf.anchor.measure),
                        leaf.anchor.position.value,
                    )
                    ties.extend(r for r in note.relations if isinstance(r, Tie) and r.start is note)

    return sorted((places[tie.start], places[tie.end]) for tie in ties)


def _leaves(containers):  # type: ignore[no-untyped-def]
    for container in containers:
        if isinstance(container, LeafRhythmicContainer):
            yield container
        else:
            yield from _leaves(container.children)


def _issues(built: BuiltScore, kind: IssueKind) -> list[ImportIssue]:
    return [issue for issue in built.issues if issue.kind is kind]


def test_notes_sound_as_written_on_both_staffs_with_a_chord_and_two_voices() -> None:
    first: str = _measure(
        1,
        attributes=_attributes(),
        body=(
            _note("C", 5)
            + _note("E", 5, alter=-1)
            + _note("G", 5, chord=True)
            + _note("B", 5, chord=True)
            + _rest()
            + "<backup><duration>6</duration></backup>"
            + _note("C", 3, duration=6, kind="half", extra="<dot/>", voice=2, staff=2)
        ),
    )

    built: BuiltScore = _build(first)

    assert _sounding(built.document) == [
        (0, Fraction(0), 0, 0, 72),
        (0, Fraction(0), 1, 1, 48),
        (0, Fraction(1, 4), 0, 0, 75),
        (0, Fraction(1, 4), 0, 0, 79),
        (0, Fraction(1, 4), 0, 0, 83),
    ]
    assert built.issues == ()


def test_measures_get_their_own_time_signatures_and_a_pickup_a_length_of_its_own() -> None:
    pickup: str = _measure(1, attributes=_attributes(beats=4), body=_note("C", 5), implicit=True)
    waltz: str = _measure(2, body=_note("D", 5, duration=8, kind="whole"))
    compound: str = _measure(
        3,
        attributes=_attributes(beats=6, beat_type=8),
        body=_note("E", 5, duration=6, kind="half", extra="<dot/>"),
    )

    built: BuiltScore = _build(pickup, waltz, compound)

    assert [str(measure.time_signature.fraction) for measure in built.document.measures] == [
        "1/4",
        "1",
        "3/4",
    ]
    assert [issue.message for issue in _issues(built, IssueKind.CHANGED)] == [
        "A pickup measure got a time signature of its own."
    ]
    assert len(built.document.measures) == 3


def test_a_clef_change_keeps_the_notes_sounding_as_written() -> None:
    low: str = _measure(
        1,
        attributes=_attributes(),
        body=_note("C", 4, duration=6, kind="half", extra="<dot/>"),
    )
    bass: str = _measure(
        2,
        attributes=_attributes(extra="").replace(
            '<clef number="1"><sign>G</sign><line>2</line></clef>',
            '<clef number="1"><sign>F</sign><line>4</line></clef>',
        ),
        body=_note("C", 3, duration=6, kind="half", extra="<dot/>"),
    )

    built: BuiltScore = _build(low, bass)

    assert [item[4] for item in _sounding(built.document)] == [60, 48]
    first_staff = built.document.staffs[0]
    clefs: list[Clef] = [
        context.clef
        for measure in built.document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if getattr(context, "staff", None) is first_staff and hasattr(context, "clef")
    ]
    assert clefs == [Clef.TREBLE, Clef.BASS]


def test_a_key_signature_is_set_and_does_not_change_the_sounding_pitch() -> None:
    notes: str = _note("F", 4, alter=1, duration=6, kind="half", extra="<dot/>")

    built: BuiltScore = _build(_measure(1, attributes=_attributes(fifths=1), body=notes))

    assert [item[4] for item in _sounding(built.document)] == [66]


def test_more_than_four_voices_are_all_imported() -> None:
    body: str = "".join(
        _note("C", 4 + voice // 3, voice=voice, duration=6, kind="half", extra="<dot/>")
        + "<backup><duration>6</duration></backup>"
        for voice in range(1, 6)
    )

    built: BuiltScore = _build(_measure(1, attributes=_attributes(), body=body))

    assert len(built.document.voices) == 5
    assert sorted({item[2] for item in _sounding(built.document)}) == [0, 1, 2, 3, 4]


def test_a_note_past_the_end_of_its_measure_and_an_overlap_are_left_out() -> None:
    body: str = (
        _note("C", 5, duration=4, kind="half")
        + _note("E", 5, duration=4, kind="half")
        + "<backup><duration>8</duration></backup>"
        + _note("G", 5, duration=3, kind="quarter", extra="<dot/>")
    )

    built: BuiltScore = _build(_measure(1, attributes=_attributes(), body=body))

    assert [item[4] for item in _sounding(built.document)] == [72]
    assert len(_issues(built, IssueKind.SKIPPED)) == 2


def test_a_time_signature_the_score_cannot_count_in_is_refused() -> None:
    with pytest.raises(ImportRefusedError, match="64ths"):
        _build(_measure(1, attributes=_attributes(beat_type=64), body=_note("C", 5)))


def test_ties_inside_a_measure_and_over_a_barline_are_made() -> None:
    first: str = _measure(
        1,
        attributes=_attributes(beats=4),
        body=(
            _note("C", 5, extra="<tie type='start'/>")
            + _note("C", 5, extra="<tie type='stop'/><tie type='start'/>")
            + _note("C", 5, extra="<tie type='stop'/>")
            + _note("D", 5, extra="<tie type='start'/>")
        ),
    )
    second: str = _measure(2, body=_note("D", 5, extra="<tie type='stop'/>"))

    built: BuiltScore = _build(first, second)

    assert _ties(built.document) == [
        ((0, Fraction(0)), (0, Fraction(1, 4))),
        ((0, Fraction(1, 4)), (0, Fraction(1, 2))),
        ((0, Fraction(3, 4)), (1, Fraction(0))),
    ]
    assert built.issues == ()


def test_a_tie_with_no_partner_is_left_out_and_reported() -> None:
    body: str = _note("C", 5, extra="<tie type='start'/>") + _note("D", 5)

    built: BuiltScore = _build(_measure(1, attributes=_attributes(), body=body))

    assert _ties(built.document) == []
    assert [issue.message for issue in _issues(built, IssueKind.SKIPPED)] == [
        "A tie with no note to join, or to a note that is not imported, is not imported."
    ]


_TRIPLET: str = (
    "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
    "</time-modification>"
)


def test_a_triplet_with_a_chord_and_a_rest_sounds_as_written() -> None:
    body: str = (
        _note("C", 5, duration=2, kind="eighth", extra=_TRIPLET)
        + _note("E", 5, duration=2, kind="eighth", chord=True, extra=_TRIPLET)
        + _note("D", 5, duration=2, kind="eighth", extra=_TRIPLET)
        + (
            "<note><rest/><duration>2</duration><voice>1</voice><type>eighth</type>"
            + _TRIPLET
            + "<staff>1</staff></note>"
        )
        + _note("G", 5, duration=12, kind="half")
    )

    built: BuiltScore = _build(_measure(1, attributes=_attributes(beats=4, divisions=6), body=body))

    assert [(item[1], item[4]) for item in _sounding(built.document)] == [
        (Fraction(0), 72),
        (Fraction(0), 76),
        (Fraction(1, 12), 74),
        (Fraction(1, 4), 79),
    ]
    assert built.issues == ()


def test_a_tuplet_that_is_not_whole_leaves_a_gap_the_score_cannot_write() -> None:
    body: str = (
        _note("C", 5, duration=2, kind="eighth", extra=_TRIPLET)
        + _note("D", 5, duration=2, kind="eighth", extra=_TRIPLET)
        + _note("G", 5, duration=12, kind="half")
    )

    with pytest.raises(ImportRefusedError, match="cannot be written"):
        _build(_measure(1, attributes=_attributes(beats=4, divisions=6), body=body))


def test_a_triplet_of_a_quarter_and_an_eighth_is_made_as_one_tuplet() -> None:
    body: str = _note("C", 5, duration=4, kind="quarter", extra=_TRIPLET) + _note(
        "D", 5, duration=2, kind="eighth", extra=_TRIPLET
    )
    body += _note("G", 5, duration=12, kind="half")

    built: BuiltScore = _build(_measure(1, attributes=_attributes(beats=4, divisions=6), body=body))

    assert [(item[1], item[4]) for item in _sounding(built.document)] == [
        (Fraction(0), 72),
        (Fraction(1, 6), 74),
        (Fraction(1, 4), 79),
    ]
    assert built.issues == ()


def _graces(document: ScoreDocument) -> list[tuple[str, str, list[list[int]]]]:
    """Every grace group as (its kind, where it stands, the MIDI numbers of its items)."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    found: list[tuple[str, str, list[list[int]]]] = []
    for voice in document.voices:
        for leaf in _leaves(voice.children):
            for where, group in (("before", leaf.grace_before), ("after", leaf.grace_after)):
                if group is None:
                    continue

                items: list[list[int]] = [
                    [pitch.pitch_of(note=note).midi_note for note in item.carrier.notes]
                    for item in group.grace_items
                    if isinstance(item.carrier, NoteCarrier)
                ]
                found.append(
                    (str(group.grace_type), f"{where} {leaf.anchor.position.value}", items)
                )

    return found


def test_grace_notes_before_and_after_a_note_are_attached_in_order() -> None:
    body: str = (
        "<note><grace slash='yes'/><pitch><step>D</step><octave>5</octave></pitch>"
        "<voice>1</voice><type>32nd</type><staff>1</staff></note>"
        "<note><grace slash='yes'/><pitch><step>E</step><octave>5</octave></pitch>"
        "<voice>1</voice><type>32nd</type><staff>1</staff></note>"
        "<note><grace slash='yes'/><chord/><pitch><step>G</step><octave>5</octave></pitch>"
        "<voice>1</voice><type>32nd</type><staff>1</staff></note>"
        + _note("C", 5, duration=4, kind="half")
        + _note("A", 4, duration=2, kind="quarter")
        + "<note><grace/><pitch><step>B</step><octave>4</octave></pitch>"
        "<voice>1</voice><type>32nd</type><staff>1</staff></note>"
    )

    built: BuiltScore = _build(_measure(1, attributes=_attributes(beats=4), body=body))

    assert _graces(built.document) == [
        ("acciaccatura", "before 0", [[74], [76, 79]]),
        ("appoggiatura", "after 1/2", [[71]]),
    ]
    assert [item[4] for item in _sounding(built.document)] == [72, 69]


def test_a_grace_note_that_does_not_fit_its_note_or_has_none_is_left_out() -> None:
    body: str = (
        "<note><grace/><pitch><step>D</step><octave>5</octave></pitch>"
        "<voice>1</voice><type>quarter</type><staff>1</staff></note>"
        + _note("C", 5, duration=1, kind="eighth")
        + _note("E", 5, duration=1, kind="eighth")
        + (
            "<backup><duration>2</duration></backup>"
            "<note><grace/><pitch><step>F</step><octave>5</octave></pitch>"
            "<voice>2</voice><type>eighth</type><staff>1</staff></note>"
        )
    )

    built: BuiltScore = _build(_measure(1, attributes=_attributes(beats=4), body=body))

    assert _graces(built.document) == []
    assert len(_issues(built, IssueKind.SKIPPED)) == 2


def test_a_note_value_the_score_has_not_got_is_left_out_and_reported() -> None:
    body: str = _note("F", 5, duration=1, kind="64th") + _note("G", 5, duration=2)

    built: BuiltScore = _build(_measure(1, attributes=_attributes(), body=body))

    assert [item[4] for item in _sounding(built.document)] == [79]
    assert [issue.message for issue in _issues(built, IssueKind.SKIPPED)] == [
        "A 64th note value is not imported."
    ]


def _direction(body: str, *, staff: int = 1) -> str:
    return f"<direction><direction-type>{body}</direction-type><staff>{staff}</staff></direction>"


def _dynamic(name: str) -> str:
    return _direction(f"<dynamics><{name}/></dynamics>")


def _wedge(kind: str) -> str:
    return _direction(f'<wedge type="{kind}"/>')


def _contexts[T: Context](document: ScoreDocument, kind: type[T]) -> list[T]:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    return [context for context in contexts.contexts() if isinstance(context, kind)]


def _at(document: ScoreDocument, anchor: TemporalAnchor | None) -> tuple[int, Fraction] | None:
    if anchor is None:
        return None

    return document.measures.index(anchor.measure), anchor.position.value


def _beams(document: ScoreDocument) -> list[list[tuple[int, Fraction]]]:
    """Every beam as the (measure, position) of each of its members, in order."""
    carriers: list[NoteCarrier] = []
    places: dict[object, tuple[int, Fraction]] = {}
    for voice in document.voices:
        for leaf in _leaves(voice.children):
            if isinstance(leaf.carrier, NoteCarrier):
                carriers.append(leaf.carrier)
                places[leaf.carrier] = (
                    document.measures.index(leaf.anchor.measure),
                    leaf.anchor.position.value,
                )

    return sorted(
        [places[member] for member in beam.members] for beam in find_beams(carriers=carriers)
    )


def _eighths(*groups: str) -> str:
    """Eighth notes, one for each state of a beam given: ``b`` begin, ``c`` continue, ``e`` end and
    ``-`` for a note that is not beamed."""
    names: dict[str, str] = {"b": "begin", "c": "continue", "e": "end"}
    steps: str = "CDEFGABC"
    body: str = ""
    for index, state in enumerate("".join(groups)):
        beam: str = f'<beam number="1">{names[state]}</beam>' if state in names else ""
        body += _note(steps[index], 5, duration=1, kind="eighth", extra=beam)

    return body


def test_the_beams_are_the_files_own_and_not_grown_by_the_engine() -> None:
    document: ScoreDocument = _build(
        _measure(1, attributes=_attributes(beats=4), body=_eighths("bce", "bce", "be"))
    ).document

    assert _beams(document) == [
        [(0, Fraction(0)), (0, Fraction(1, 8)), (0, Fraction(1, 4))],
        [(0, Fraction(3, 8)), (0, Fraction(1, 2)), (0, Fraction(5, 8))],
        [(0, Fraction(3, 4)), (0, Fraction(7, 8))],
    ]


def test_a_note_the_file_does_not_beam_stands_alone_and_a_gap_cuts_a_beam() -> None:
    gap: str = _measure(
        1,
        attributes=_attributes(beats=4),
        body=(
            _eighths("--")
            + _note("E", 5, duration=1, kind="eighth", extra='<beam number="1">begin</beam>')
            + _rest(duration=1, kind="eighth")
            + _note("G", 5, duration=1, kind="eighth", extra='<beam number="1">end</beam>')
            + _note("A", 5, duration=1, kind="eighth", extra='<beam number="1">begin</beam>')
            + _note("B", 5, duration=1, kind="eighth", extra='<beam number="1">end</beam>')
            + _rest(duration=2)
        ),
    )

    assert _beams(_build(gap).document) == [[(0, Fraction(5, 8)), (0, Fraction(3, 4))]]


def test_the_direction_of_every_stem_the_file_draws_is_kept() -> None:
    body: str = (
        _note("C", 5, extra="<stem>down</stem>")
        + _note("E", 5, extra="<stem>up</stem>")
        + _note("G", 5, chord=True, extra="<stem>up</stem>")
        + _note("A", 5, duration=2, kind="half", extra="<stem>none</stem>")
    )

    document: ScoreDocument = _build(
        _measure(1, attributes=_attributes(beats=4), body=body)
    ).document

    places: dict[str, Fraction] = {}
    for leaf in _leaves(document.voices[0].children):
        if isinstance(leaf.carrier, NoteCarrier):
            places[leaf.carrier.id] = leaf.anchor.position.value

    assert sorted(
        (places[target.entity_id], direction)
        for target, direction in document.presentation.directions.items()
    ) == [
        (Fraction(0), StemDirection.DOWN),
        (Fraction(1, 4), StemDirection.UP),
    ]


def test_different_dynamics_on_the_two_staffs_stay_and_the_same_one_is_the_pieces() -> None:
    body: str = (
        _note("C", 5)
        + _note("D", 5, duration=4, kind="half")
        + "<backup><duration>6</duration></backup>"
        + _note("C", 3, duration=6, kind="half", voice=2, staff=2, extra="<dot/>")
    )
    different: str = _measure(
        1,
        attributes=_attributes(),
        body=_direction("<dynamics><mf/></dynamics>", staff=1)
        + _direction("<dynamics><p/></dynamics>", staff=2)
        + body,
    )
    same: str = _measure(
        2,
        body=_direction("<dynamics><f/></dynamics>", staff=1)
        + _direction("<dynamics><f/></dynamics>", staff=2)
        + body,
    )

    document: ScoreDocument = _build(different, same).document

    voices: dict[str, int] = {voice.id: index for index, voice in enumerate(document.voices)}
    # the voices of the two staffs are the first two; the others hold the engine's own start level
    found: list[tuple[tuple[int, Fraction] | None, str, list[int]]] = [
        (
            _at(document, dynamic.start),
            dynamic.dynamic.value,
            sorted(voices[v.id] for v in dynamic.voices),
        )
        for dynamic in _contexts(document, DynamicChange)
        if {0, 1} & {voices[v.id] for v in dynamic.voices}
    ]
    assert sorted(found, key=str) == [
        ((0, Fraction(0)), "mf", [0]),
        ((0, Fraction(0)), "p", [1]),
        ((1, Fraction(0)), "f", [0, 1, 2, 3]),
    ]


def test_a_voice_that_crosses_the_staffs_takes_the_dynamic_of_the_staff_it_plays_on_there() -> None:
    backup: str = "<backup><duration>6</duration></backup>"
    body: str = (
        _direction("<dynamics><mf/></dynamics>", staff=1)
        + _direction("<dynamics><p/></dynamics>", staff=2)
        + _note("C", 5, duration=6, kind="half", extra="<dot/>")
        + backup
        + _note("D", 5, voice=2, staff=1)
        + _note("E", 3, duration=4, kind="half", voice=2, staff=2)
        + backup
        + _note("C", 3, duration=6, kind="half", voice=3, staff=2, extra="<dot/>")
    )

    document: ScoreDocument = _build(_measure(1, attributes=_attributes(), body=body)).document

    voices: dict[str, int] = {voice.id: index for index, voice in enumerate(document.voices)}
    assert sorted(
        (dynamic.dynamic.value, sorted(voices[v.id] for v in dynamic.voices))
        for dynamic in _contexts(document, DynamicChange)
        if {0, 1, 2} & {voices[v.id] for v in dynamic.voices}
    ) == [("mf", [0, 1]), ("p", [2])]


def test_dynamics_and_a_hairpin_to_the_next_dynamic_are_imported() -> None:
    first: str = _measure(
        1,
        attributes=_attributes(),
        body=(
            _dynamic("mf")
            + _wedge("crescendo")
            + _note("C", 5)
            + _note("D", 5)
            + _wedge("stop")
            + _note("E", 5)
            + _dynamic("ff")
        ),
    )

    built: BuiltScore = _build(
        first, _measure(2, body=_note("C", 5, duration=6, kind="half", extra="<dot/>"))
    )

    document: ScoreDocument = built.document
    assert [(_at(document, d.start), d.dynamic) for d in _contexts(document, DynamicChange)][
        -2:
    ] == [
        ((0, Fraction(0)), DynamicMarking.MEZZO_FORTE),
        ((1, Fraction(0)), DynamicMarking.FORTISSIMO),
    ]
    (hairpin,) = _contexts(document, Hairpin)
    assert (_at(document, hairpin.start), _at(document, hairpin.end), hairpin.steps) == (
        (0, Fraction(0)),
        (0, Fraction(1, 2)),
        2,
    )
    assert built.issues == ()


def test_a_hairpin_the_score_cannot_state_is_reported_with_its_measure() -> None:
    inside: str = _measure(
        1,
        attributes=_attributes(),
        body=(
            _wedge("crescendo")
            + _note("C", 5)
            + _dynamic("f")
            + _note("D", 5)
            + _wedge("stop")
            + _note("E", 5)
            + _dynamic("ff")
        ),
    )
    no_target: str = _measure(
        2,
        body=_wedge("diminuendo") + _note("C", 5) + _note("D", 5) + _wedge("stop") + _note("E", 5),
    )
    open_end: str = _measure(
        3, body=_wedge("crescendo") + _note("C", 5, duration=6, kind="half", extra="<dot/>")
    )

    built: BuiltScore = _build(inside, no_target, open_end)

    assert _contexts(built.document, Hairpin) == []
    assert [(issue.measure, issue.message) for issue in _issues(built, IssueKind.SKIPPED)] == [
        ("1", "A crescendo hairpin that has a dynamic inside it is not imported."),
        ("2", "A diminuendo hairpin that has no dynamic after it to reach is not imported."),
        ("3", "A crescendo hairpin that never ends is not imported."),
    ]


def test_a_dynamic_the_score_has_no_sign_for_is_reported() -> None:
    built: BuiltScore = _build(
        _measure(
            1,
            attributes=_attributes(),
            body=_dynamic("sfz") + _note("C", 5, duration=6, kind="half", extra="<dot/>"),
        )
    )

    assert [(i.measure, i.message) for i in _issues(built, IssueKind.SKIPPED)] == [
        ("1", "The dynamic sfz is not imported.")
    ]


def test_a_tempo_and_a_slur_across_a_barline_and_a_pedal_are_imported() -> None:
    first: str = _measure(
        1,
        attributes=_attributes(),
        body=(
            _direction(
                "<metronome><beat-unit>quarter</beat-unit><beat-unit-dot/>"
                "<per-minute>60</per-minute></metronome>"
            )
            + _direction('<pedal type="start"/>')
            + _note("C", 5, extra="<notations><slur type='start' number='1'/></notations>")
            + _note("D", 5)
            + _note("E", 5)
        ),
    )
    second: str = _measure(
        2,
        body=(
            _note("F", 5, extra="<notations><slur type='stop' number='1'/></notations>")
            + _direction('<pedal type="stop"/>')
            + _note("G", 5)
            + _note("A", 5)
        ),
    )

    built: BuiltScore = _build(first, second)

    document: ScoreDocument = built.document
    tempos = _contexts(document, TempoChange)
    assert [(t.bpm, t.beat.dots_count) for t in tempos if t.bpm == 60] == [(60, 1)]
    (slur,) = _contexts(document, Slur)
    assert (_at(document, slur.start), _at(document, slur.end)) == (
        (0, Fraction(0)),
        (1, Fraction(0)),
    )
    (pedal,) = _contexts(document, SustainHold)
    assert (_at(document, pedal.start), _at(document, pedal.end)) == (
        (0, Fraction(0)),
        (1, Fraction(1, 4)),
    )
    assert built.issues == ()


def test_a_pedal_never_let_up_ends_at_the_last_note() -> None:
    built: BuiltScore = _build(
        _measure(
            1,
            attributes=_attributes(),
            body=_direction('<pedal type="start"/>')
            + _note("C", 5)
            + _note("D", 5)
            + _note("E", 5),
        )
    )

    (pedal,) = _contexts(built.document, SustainHold)
    assert (_at(built.document, pedal.start), _at(built.document, pedal.end)) == (
        (0, Fraction(0)),
        (0, Fraction(1, 2)),
    )


def test_an_octave_line_keeps_the_notes_sounding_as_written_and_may_last_to_the_end() -> None:
    first: str = _measure(
        1,
        attributes=_attributes(),
        body=(
            _direction('<octave-shift type="down" size="8"/>')
            + _note("C", 5)
            + _note("D", 5)
            + _note("E", 5)
            + _direction('<octave-shift type="stop" size="8"/>')
        ),
    )
    second: str = _measure(
        2,
        body=(
            _direction('<octave-shift type="up" size="8"/>')
            + _note("C", 3)
            + _note("D", 3)
            + _note("E", 3)
        ),
    )

    built: BuiltScore = _build(first, second)

    document: ScoreDocument = built.document
    assert [item[4] for item in _sounding(document)] == [72, 74, 76, 48, 50, 52]
    lines = _contexts(document, OctaveTransposition)
    assert [
        (line.octaves, _at(document, line.start), _at(document, line.end)) for line in lines
    ] == [
        (1, (0, Fraction(0)), (1, Fraction(0))),
        (-1, (1, Fraction(0)), None),
    ]


def test_articulations_ornaments_and_fingerings_are_put_on_the_notes() -> None:
    marks: str = (
        "<notations><articulations><staccato/><accent/></articulations>"
        "<ornaments><inverted-mordent/></ornaments><technical><fingering>3</fingering></technical>"
        "<fermata/></notations>"
    )
    built: BuiltScore = _build(
        _measure(
            1,
            attributes=_attributes(),
            body=_note("C", 5, extra=marks) + _note("D", 5) + _note("E", 5),
        )
    )

    document: ScoreDocument = built.document
    first = next(_leaves(document.voices[0].children))
    assert isinstance(first.carrier, NoteCarrier)
    assert first.carrier.articulations == {Articulation.STACCATO, Articulation.ACCENT}
    assert first.carrier.ornament is Ornament.UPPER_MORDENT
    assert [note.fingering for note in first.carrier.notes] == [Fingering.MIDDLE]
    assert [(i.measure, i.message) for i in _issues(built, IssueKind.SKIPPED)] == [
        ("1", "A note has one mark of its kind only: fermata is not imported.")
    ]


_BAR: str = _note("C", 5, duration=6, kind="half", extra="<dot/>")


def _left(inner: str) -> str:
    return f'<barline location="left">{inner}</barline>'


def _right(inner: str) -> str:
    return f'<barline location="right">{inner}</barline>'


def test_a_repeat_runs_from_its_forward_sign_to_its_backward_sign() -> None:
    built: BuiltScore = _build(
        _measure(1, attributes=_attributes(), body=_BAR),
        _measure(2, body=_left('<repeat direction="forward"/>') + _BAR),
        _measure(3, body=_BAR + _right('<repeat direction="backward" times="3"/>')),
        _measure(4, body=_BAR),
    )

    (refrain,) = _contexts(built.document, Refrain)
    assert (
        _at(built.document, refrain.start),
        _at(built.document, refrain.end),
        refrain.times,
    ) == (
        (1, Fraction(0)),
        (3, Fraction(0)),
        3,
    )


def test_a_backward_sign_with_no_forward_sign_repeats_from_the_start_and_may_end_the_score() -> (
    None
):
    built: BuiltScore = _build(
        _measure(1, attributes=_attributes(), body=_BAR + _right('<repeat direction="backward"/>')),
        _measure(2, body=_BAR),
        _measure(3, body=_BAR + _right('<repeat direction="backward"/>')),
    )

    refrains = _contexts(built.document, Refrain)
    assert [
        (_at(built.document, r.start), _at(built.document, r.end), r.times) for r in refrains
    ] == [
        ((0, Fraction(0)), (1, Fraction(0)), 2),
        ((1, Fraction(0)), None, 2),
    ]


def test_endings_make_a_volta_with_the_stretch_before_them_as_its_body() -> None:
    built: BuiltScore = _build(
        _measure(1, attributes=_attributes(), body=_left('<repeat direction="forward"/>') + _BAR),
        _measure(
            2,
            body=(
                _left('<ending number="1" type="start"/>')
                + _BAR
                + _right('<ending number="1" type="stop"/><repeat direction="backward"/>')
            ),
        ),
        _measure(
            3,
            body=(
                _left('<ending number="2" type="start"/>')
                + _BAR
                + _right('<ending number="2" type="discontinue"/>')
            ),
        ),
    )

    (volta,) = _contexts(built.document, Volta)
    document: ScoreDocument = built.document
    assert _at(document, volta.start) == (0, Fraction(0))
    assert _at(document, volta.body_end) == (1, Fraction(0))
    assert [
        (_at(document, f.start), _at(document, f.end), set(f.passes)) for f in volta.fragments
    ] == [
        ((1, Fraction(0)), (2, Fraction(0)), {1}),
    ]
    assert volta.pass_count == 2
    assert _contexts(document, Refrain) == []
    assert built.issues == ()


def test_a_mark_the_engine_refuses_is_left_out_and_the_rest_stays() -> None:
    built: BuiltScore = _build(
        _measure(
            1,
            attributes=_attributes(),
            body=(
                _wedge("crescendo")
                + _wedge("stop")
                + _note("C", 5, duration=6, kind="half", extra="<dot/>")
                + _dynamic("f")
            ),
        ),
        _measure(
            2,
            body=(
                _wedge("crescendo")
                + _note("D", 5)
                + _wedge("stop")
                + _note("E", 5)
                + _note("F", 5)
                + _dynamic("ff")
            ),
        ),
    )

    document: ScoreDocument = built.document
    assert [(h.steps, _at(document, h.start)) for h in _contexts(document, Hairpin)] == [
        (1, (1, Fraction(0)))
    ]
    assert [(i.measure, i.message) for i in _issues(built, IssueKind.SKIPPED)] == [
        ("1", "A hairpin is not imported: A hairpin must end after it starts.")
    ]
    assert len(_sounding(document)) == 4
