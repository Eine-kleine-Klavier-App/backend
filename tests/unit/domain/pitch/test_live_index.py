from fractions import Fraction
from random import Random

import pytest

from piano_app.domain.score.document.models.context import ClefChange, OctaveTransposition
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch import (
    PitchResolutionError,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .test_score_pitch import PitchScene, build_scene


def reference_pitch(
    scene: PitchScene, staff: Staff, at: Fraction, step: int, accidental: Accidental
) -> int:
    # Deliberately independent of geometry and the numeric origin/table in PitchTransform.
    starts: dict[Measure, Fraction] = {}
    cursor = Fraction(0)
    for measure in scene.document.measures:
        starts[measure] = cursor
        cursor += measure.time_signature.fraction
    active: ClefChange | None = None
    latest = Fraction(-1)
    shift = 0
    for context in staff.contexts:
        start = starts[context.start.measure] + context.start.position.value
        if isinstance(context, ClefChange) and latest <= start <= at:
            active, latest = context, start
        elif isinstance(context, OctaveTransposition):
            end = starts[context.end.measure] + context.end.position.value
            if start <= at < end:
                shift += context.octaves
    assert active is not None
    if active.clef == Clef.TREBLE:
        base, intervals = 64, (0, 1, 3, 5, 7, 8, 10)
    else:
        base, intervals = 43, (0, 2, 4, 5, 7, 9, 10)
    octave, position = divmod(step, 7)
    alteration = {
        Accidental.DOUBLE_FLAT: -2,
        Accidental.FLAT: -1,
        Accidental.NATURAL: 0,
        Accidental.SHARP: 1,
        Accidental.DOUBLE_SHARP: 2,
    }[accidental]
    return (
        base
        + intervals[position]
        + alteration
        + 12 * (octave + shift + active.octave_transposition)
    )


def assert_current(scene: PitchScene) -> None:
    fresh_geometry = ScoreGeometry(document=scene.document)
    fresh = ScorePitch(
        document=scene.document,
        geometry=fresh_geometry,
        contexts=ContextIndex(document=scene.document, geometry=fresh_geometry),
    )
    extent = fresh_geometry.root.extent
    positions = {Fraction(i, 8) for i in range(int(extent * 8) + 1)}
    cursor = Fraction(0)
    for measure in scene.document.measures:
        for anchor in measure.anchors:
            at = cursor + anchor.position.value
            positions.update((at - Fraction(1, 10000), at, at + Fraction(1, 10000)))
        cursor += measure.time_signature.fraction
    for staff in scene.document.staffs:
        for at in sorted(position for position in positions if 0 <= position < extent):
            for step in (-9, -2, 0, 3, 8):
                for accidental in Accidental:
                    actual = scene.resolve(at, staff=staff, step=step, accidental=accidental)
                    expected = fresh.resolve(
                        staff=staff,
                        point=Point(frame=fresh_geometry.root, value=at),
                        staff_step=step,
                        accidental=accidental,
                    )
                    assert actual == expected
                    assert actual.midi_note == reference_pitch(scene, staff, at, step, accidental)


@pytest.mark.parametrize(
    "edit",
    [
        "create clef",
        "delete clef",
        "move clef context",
        "move clef anchor",
        "create octave",
        "delete octave",
        "move octave start",
        "move octave end",
        "move start anchor",
        "move end anchor",
        "insert measure",
        "remove empty measure",
        "append measure",
        "change time signature",
        "insert first measure",
    ],
)
def test_delivered_mutations_match_fresh_and_independent_answers(edit: str) -> None:
    scene = build_scene()
    clef = ClefChange.create(start=scene.anchor(Fraction(2)), staff=scene.upper, clef=Clef.BASS)
    octave = OctaveTransposition.create(
        start=scene.anchor(Fraction(1, 4)),
        end=scene.anchor(Fraction(3, 2)),
        staff=scene.upper,
        octaves=1,
    )
    assert_current(scene)

    if edit == "create clef":
        ClefChange.create(
            start=scene.anchor(Fraction(3)),
            staff=scene.upper,
            clef=Clef.TREBLE,
            octave_transposition=-1,
        )
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "delete clef":
        clef.detach()
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "move clef context":
        clef.set_start(start=scene.anchor(Fraction(3)))
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "move clef anchor":
        clef.start.move_to(
            measure=scene.document.measures[2], position=MeasurePosition(value=Fraction(1, 2))
        )
        scene.geometry.invalidate_anchor(anchor=clef.start)
        scene.pitch.invalidate_anchor(anchor=clef.start)
    elif edit == "create octave":
        OctaveTransposition.create(
            start=scene.anchor(Fraction(2)),
            end=scene.anchor(Fraction(3)),
            staff=scene.upper,
            octaves=-2,
        )
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "delete octave":
        octave.detach()
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "move octave start":
        octave.set_start(start=scene.anchor(Fraction(1, 2)))
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "move octave end":
        octave.set_end(end=scene.anchor(Fraction(7, 4)))
        scene.pitch.invalidate_staff(staff=scene.upper)
    elif edit == "move start anchor":
        octave.start.move_to(
            measure=scene.document.measures[0], position=MeasurePosition(value=Fraction(1, 2))
        )
        scene.geometry.invalidate_anchor(anchor=octave.start)
        scene.pitch.invalidate_anchor(anchor=octave.start)
    elif edit == "move end anchor":
        octave.end.move_to(
            measure=scene.document.measures[1], position=MeasurePosition(value=Fraction(3, 4))
        )
        scene.geometry.invalidate_anchor(anchor=octave.end)
        scene.pitch.invalidate_anchor(anchor=octave.end)
    else:
        if edit == "insert measure":
            scene.document.insert_measure_before(
                measure=Measure.create(), before=scene.document.measures[1]
            )
        elif edit == "remove empty measure":
            scene.document.remove_measure(measure=scene.document.measures[3])
        elif edit == "append measure":
            scene.document.append_measure(measure=Measure.create())
        elif edit == "change time signature":
            scene.document.measures[0].set_time_signature(
                time_signature=RhythmicSize(
                    value=DottedRhythmicValue(value=RhythmicValue.WHOLE), count=2
                )
            )
        elif edit == "insert first measure":
            scene.document.insert_measure_before(
                measure=Measure.create(), before=scene.document.measures[0]
            )
            # The caller maintains the initial-clef precondition at the new origin.
            start = scene.anchor(Fraction(0))
            ClefChange.create(start=start, staff=scene.upper, clef=Clef.TREBLE)
            ClefChange.create(start=start, staff=scene.lower, clef=Clef.BASS)
        else:
            raise AssertionError(edit)
        scene.geometry.invalidate_measures()
        scene.pitch.invalidate_measures()
    assert_current(scene)


def test_a_staff_fragment_is_reused_and_a_change_rebuilds_only_its_staff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = build_scene()
    anchors = {"read": 0}
    original_point = ScoreGeometry.point_of

    def point_of(self: ScoreGeometry, *, anchor: TemporalAnchor) -> Point:
        anchors["read"] += 1
        return original_point(self, anchor=anchor)

    monkeypatch.setattr(ScoreGeometry, "point_of", point_of)
    assert anchors == {"read": 0}
    upper = scene.resolve(Fraction(1))
    lower = scene.resolve(Fraction(1), staff=scene.lower)
    warm = anchors["read"]
    assert scene.resolve(Fraction(1)) == upper
    assert scene.resolve(Fraction(1), staff=scene.lower) == lower
    assert anchors["read"] == warm

    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    scene.pitch.invalidate_staff(staff=scene.upper)
    assert anchors["read"] == warm  # invalidation is lazy
    assert scene.resolve(Fraction(1), staff=scene.lower) == lower
    assert anchors["read"] == warm
    assert scene.resolve(Fraction(1)).midi_note == 43
    assert anchors["read"] > warm


def test_each_query_input_changes_the_answer() -> None:
    scene = build_scene()
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    assert scene.resolve(Fraction(0)).midi_note == 64
    assert scene.resolve(Fraction(0), step=1).midi_note == 65
    assert scene.resolve(Fraction(0), accidental=Accidental.FLAT).midi_note == 63
    assert scene.resolve(Fraction(1)).midi_note == 43
    assert scene.resolve(Fraction(0), staff=scene.lower).midi_note == 43


def test_shared_anchor_invalidates_all_affected_staffs() -> None:
    scene = build_scene()
    anchor = scene.anchor(Fraction(1))
    ClefChange.create(start=anchor, staff=scene.upper, clef=Clef.BASS)
    ClefChange.create(start=anchor, staff=scene.lower, clef=Clef.TREBLE)
    assert_current(scene)
    anchor.move_to(
        measure=scene.document.measures[1], position=MeasurePosition(value=Fraction(1, 2))
    )
    scene.geometry.invalidate_anchor(anchor=anchor)
    scene.pitch.invalidate_anchor(anchor=anchor)
    assert_current(scene)


def test_without_notification_a_warmed_answer_is_stale_until_invalidated() -> None:
    scene = build_scene()
    assert scene.resolve(Fraction(1)).midi_note == 64
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    assert scene.resolve(Fraction(1)).midi_note == 64
    scene.pitch.invalidate_staff(staff=scene.upper)
    assert scene.resolve(Fraction(1)).midi_note == 43


def test_replacement_and_repeated_context_moves() -> None:
    scene = build_scene()
    clef = ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    assert_current(scene)
    clef.detach()
    clef = ClefChange.create(
        start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.TREBLE, octave_transposition=1
    )
    scene.pitch.invalidate_staff(staff=scene.upper)
    assert_current(scene)
    for at in (Fraction(7, 3), Fraction(1, 3), Fraction(3)):
        clef.set_start(start=scene.anchor(at))
        scene.pitch.invalidate_staff(staff=scene.upper)
        assert_current(scene)


def test_remove_first_measure_with_initial_clefs_preserved() -> None:
    scene = build_scene()
    later = scene.anchor(Fraction(1))
    ClefChange.create(start=scene.anchor(Fraction(2)), staff=scene.upper, clef=Clef.BASS)
    assert_current(scene)
    first = scene.document.measures[0]
    for staff in scene.document.staffs:
        for context in tuple(staff.contexts):
            if context.start.measure is first:
                context.set_start(start=later)
    scene.document.remove_measure(measure=first)
    scene.geometry.invalidate_measures()
    scene.pitch.invalidate_measures()
    assert_current(scene)
    assert scene.resolve(Fraction(1)).midi_note == 43


def test_shortening_a_measure_repositions_cached_contexts() -> None:
    scene = build_scene()
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    assert_current(scene)
    scene.document.measures[0].set_time_signature(
        time_signature=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.HALF), count=1)
    )
    scene.geometry.invalidate_measures()
    scene.pitch.invalidate_measures()
    assert_current(scene)
    assert scene.resolve(Fraction(1, 2)).midi_note == 43


@pytest.mark.parametrize("remove", [False, True])
def test_shrinking_timeline_rejects_previously_cached_tail(remove: bool) -> None:
    scene = build_scene()
    tail = Fraction(15, 4)
    assert scene.resolve(tail).midi_note == 64
    if remove:
        scene.document.remove_measure(measure=scene.document.measures[-1])
    else:
        scene.document.measures[-1].set_time_signature(
            time_signature=RhythmicSize(
                value=DottedRhythmicValue(value=RhythmicValue.HALF), count=1
            )
        )
    scene.geometry.invalidate_measures()
    scene.pitch.invalidate_measures()
    with pytest.raises(PitchResolutionError, match="outside"):
        scene.resolve(tail)
    new_end = scene.geometry.root.extent
    with pytest.raises(PitchResolutionError, match="outside"):
        scene.resolve(new_end)
    assert scene.resolve(new_end - Fraction(1, 10000)).midi_note == 64
    assert_current(scene)


def test_replacing_octave_line_discards_warmed_result() -> None:
    scene = build_scene()
    start, end = scene.anchor(Fraction(1)), scene.anchor(Fraction(2))
    previous = OctaveTransposition.create(start=start, end=end, staff=scene.upper, octaves=1)
    assert scene.resolve(Fraction(3, 2)).midi_note == 76
    lower = scene.resolve(Fraction(3, 2), staff=scene.lower)
    for at, expected in [
        (Fraction(999, 1000), 64),
        (Fraction(1), 76),
        (Fraction(1999, 1000), 76),
        (Fraction(2), 64),
    ]:
        assert scene.resolve(at).midi_note == expected
    previous.detach()
    OctaveTransposition.create(start=start, end=end, staff=scene.upper, octaves=-2)
    scene.pitch.invalidate_staff(staff=scene.upper)
    assert scene.resolve(Fraction(3, 2)).midi_note == 40
    assert scene.resolve(Fraction(3, 2), staff=scene.lower) == lower
    for at, expected in [
        (Fraction(999, 1000), 64),
        (Fraction(1), 40),
        (Fraction(1999, 1000), 40),
        (Fraction(2), 64),
    ]:
        assert scene.resolve(at).midi_note == expected
    assert_current(scene)


def test_multiple_changes_before_read_and_returned_snapshot() -> None:
    scene = build_scene()
    snapshot = scene.resolve(Fraction(1))
    clef = ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    scene.pitch.invalidate_staff(staff=scene.upper)
    clef.set_start(start=scene.anchor(Fraction(1, 2)))
    scene.pitch.invalidate_staff(staff=scene.upper)
    OctaveTransposition.create(
        start=scene.anchor(Fraction(1)), end=scene.anchor(Fraction(2)), staff=scene.upper, octaves=1
    )
    scene.pitch.invalidate_staff(staff=scene.upper)
    assert scene.resolve(Fraction(1)).midi_note == 55
    assert snapshot.midi_note == 64
    assert_current(scene)


def test_repeated_cold_invalidation_and_irrelevant_anchor() -> None:
    scene = build_scene()
    empty = scene.anchor(Fraction(1))
    for _ in range(2):
        scene.pitch.invalidate_staff(staff=scene.upper)
        scene.pitch.invalidate_anchor(anchor=empty)
        scene.pitch.invalidate_measures()
    cached = scene.resolve(Fraction(1))
    scene.pitch.invalidate_anchor(anchor=empty)
    assert scene.resolve(Fraction(1)) == cached
    assert_current(scene)


def test_anchor_is_end_and_start_for_different_staffs() -> None:
    scene = build_scene()
    shared = scene.anchor(Fraction(1))
    OctaveTransposition.create(
        start=scene.anchor(Fraction(1, 4)), end=shared, staff=scene.upper, octaves=1
    )
    OctaveTransposition.create(
        start=shared, end=scene.anchor(Fraction(2)), staff=scene.lower, octaves=-1
    )
    assert_current(scene)
    shared.move_to(
        measure=scene.document.measures[1], position=MeasurePosition(value=Fraction(1, 3))
    )
    scene.geometry.invalidate_anchor(anchor=shared)
    scene.pitch.invalidate_anchor(anchor=shared)
    assert_current(scene)
    assert scene.resolve(Fraction(1)).midi_note == 76
    assert scene.resolve(Fraction(1), staff=scene.lower).midi_note == 43


@pytest.mark.parametrize("seed", [7, 29, 20261025])
def test_random_edit_sequences_against_independent_reference(seed: int) -> None:
    scene = build_scene()
    random = Random(seed)
    clefs: dict[Staff, ClefChange] = {}
    octaves: dict[Staff, OctaveTransposition] = {}
    operations = [
        "create clef",
        "move clef",
        "replace clef",
        "create octave",
        "move octave",
        "replace octave",
        "remove clef",
        "remove octave",
    ]
    assert_current(scene)
    for turn in range(40):
        # Every operation occurs; the seed varies staff, position and payload.
        operation = operations[turn % len(operations)]
        staff = random.choice([scene.upper, scene.lower])
        if operation in ("create clef", "replace clef"):
            if operation == "replace clef":
                staff = random.choice(list(clefs))
            previous = clefs.pop(staff, None)
            if previous is not None:
                previous.detach()
            clefs[staff] = ClefChange.create(
                start=scene.anchor(Fraction(random.randint(1, 11), 3)),
                staff=staff,
                clef=random.choice(list(Clef)),
                octave_transposition=random.randint(-3, 3),
            )
        elif operation == "move clef":
            staff = random.choice(list(clefs))
            targets = [scene.anchor(Fraction(i, 3)) for i in range(1, 12)]
            target = random.choice(
                [anchor for anchor in targets if anchor is not clefs[staff].start]
            )
            clefs[staff].set_start(start=target)
        elif operation in ("create octave", "replace octave"):
            if operation == "replace octave":
                staff = random.choice(list(octaves))
            previous_octave = octaves.pop(staff, None)
            if previous_octave is not None:
                previous_octave.detach()
            octaves[staff] = OctaveTransposition.create(
                start=scene.anchor(Fraction(random.randint(1, 4), 3)),
                end=scene.anchor(Fraction(random.randint(7, 11), 3)),
                staff=staff,
                octaves=random.choice([-2, -1, 1, 2]),
            )
        elif operation == "move octave":
            staff = random.choice(list(octaves))
            starts = [scene.anchor(Fraction(i, 3)) for i in range(1, 5)]
            ends = [scene.anchor(Fraction(i, 3)) for i in range(7, 12)]
            octaves[staff].set_start(
                start=random.choice(
                    [anchor for anchor in starts if anchor is not octaves[staff].start]
                )
            )
            octaves[staff].set_end(
                end=random.choice([anchor for anchor in ends if anchor is not octaves[staff].end])
            )
        elif operation == "remove clef":
            staff = random.choice(list(clefs))
            clefs.pop(staff).detach()
        elif operation == "remove octave":
            staff = random.choice(list(octaves))
            octaves.pop(staff).detach()
        scene.pitch.invalidate_staff(staff=staff)
        assert_current(scene)
