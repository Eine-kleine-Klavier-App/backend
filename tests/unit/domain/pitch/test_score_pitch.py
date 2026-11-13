from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    KeySignatureChange,
    OctaveTransposition,
)
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
from piano_app.domain.score.document.services.geometry import Point, UnreachableFrameError
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch import Pitch, PitchResolutionError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


class _ScenePitch(ScorePitch):
    """A pitch index whose notifications also clear the context index it reads, in the order
    the index layer tells them: contexts before pitch."""

    def __init__(
        self, *, document: ScoreDocument, geometry: ScoreGeometry, contexts: ContextIndex
    ) -> None:
        super().__init__(document=document, geometry=geometry, contexts=contexts)
        self._reset: ContextIndex = contexts

    def invalidate_staff(self, *, staff: Staff) -> None:
        self._reset.invalidate_measures()
        super().invalidate_staff(staff=staff)

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        self._reset.invalidate_measures()
        super().invalidate_anchor(anchor=anchor)

    def invalidate_measures(self) -> None:
        self._reset.invalidate_measures()
        super().invalidate_measures()


@dataclass(kw_only=True)
class PitchScene:
    document: ScoreDocument
    geometry: ScoreGeometry
    contexts: ContextIndex
    pitch: ScorePitch
    upper: Staff
    lower: Staff

    def anchor(self, at: Fraction) -> TemporalAnchor:
        measure = self.document.measures[int(at)]
        position = MeasurePosition(value=at - int(at))
        for anchor in measure.anchors:
            if anchor.position == position:
                return anchor
        return TemporalAnchor.create(measure=measure, position=position)

    def resolve(
        self,
        at: Fraction,
        *,
        staff: Staff | None = None,
        step: int = 0,
        accidental: Accidental = Accidental.NATURAL,
    ) -> Pitch:
        return self.pitch.resolve(
            staff=self.upper if staff is None else staff,
            point=Point(frame=self.geometry.root, value=at),
            staff_step=step,
            accidental=accidental,
        )


def build_scene() -> PitchScene:
    upper, lower = Staff(), Staff()
    document = ScoreDocument.create(
        voices=[], staffs=[upper, lower], measures=[Measure.create() for _ in range(4)]
    )
    geometry = ScoreGeometry(document=document)
    contexts = ContextIndex(document=document, geometry=geometry)
    scene = PitchScene(
        document=document,
        geometry=geometry,
        contexts=contexts,
        pitch=_ScenePitch(document=document, geometry=geometry, contexts=contexts),
        upper=upper,
        lower=lower,
    )
    start = scene.anchor(Fraction(0))
    ClefChange.create(start=start, staff=upper, clef=Clef.TREBLE)
    ClefChange.create(start=start, staff=lower, clef=Clef.BASS)
    return scene


@pytest.mark.parametrize(
    ("step", "accidental", "upper", "lower"),
    [
        (0, Accidental.NATURAL, 64, 43),
        (0, Accidental.SHARP, 65, 44),
        (0, Accidental.FLAT, 63, 42),
        (-2, Accidental.NATURAL, 60, 40),
        (3, Accidental.NATURAL, 69, 48),
        (7, Accidental.NATURAL, 76, 55),
    ],
)
def test_real_clef_mapping_on_separate_staffs(
    step: int, accidental: Accidental, upper: int, lower: int
) -> None:
    scene = build_scene()
    assert scene.resolve(Fraction(0), step=step, accidental=accidental).midi_note == upper
    assert (
        scene.resolve(Fraction(0), staff=scene.lower, step=step, accidental=accidental).midi_note
        == lower
    )


def test_clef_shift_and_octave_bracket_both_apply() -> None:
    scene = build_scene()
    ClefChange.create(
        start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS, octave_transposition=-1
    )
    OctaveTransposition.create(
        start=scene.anchor(Fraction(1, 2)),
        end=scene.anchor(Fraction(2)),
        staff=scene.upper,
        octaves=2,
    )
    assert scene.resolve(Fraction(0)).midi_note == 64
    assert scene.resolve(Fraction(1, 2)).midi_note == 88
    assert scene.resolve(Fraction(1)).midi_note == 55
    assert scene.resolve(Fraction(2)).midi_note == 31
    assert scene.resolve(Fraction(1), staff=scene.lower).midi_note == 43


def test_key_signature_does_not_override_concrete_accidental() -> None:
    scene = build_scene()
    KeySignatureChange.create(
        start=scene.anchor(Fraction(0)),
        staff=scene.upper,
        alterations=(Accidental.SHARP,) * 7,
    )
    assert scene.resolve(Fraction(1), accidental=Accidental.NATURAL).midi_note == 64


def test_a_double_accidental_moves_the_pitch_two_semitones() -> None:
    scene = build_scene()

    natural: int = scene.resolve(Fraction(0)).midi_note

    assert scene.resolve(Fraction(0), accidental=Accidental.DOUBLE_SHARP).midi_note == natural + 2
    assert scene.resolve(Fraction(0), accidental=Accidental.DOUBLE_FLAT).midi_note == natural - 2


def test_measure_local_point_is_resolved_on_timeline() -> None:
    scene = build_scene()
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    assert (
        scene.pitch.resolve(
            staff=scene.upper,
            point=Point(
                frame=scene.geometry.of_measure(measure=scene.document.measures[1]),
                value=Fraction(0),
            ),
            staff_step=0,
            accidental=Accidental.NATURAL,
        ).midi_note
        == 43
    )


def test_no_default_clef_is_invented() -> None:
    scene = build_scene()
    for context in tuple(scene.upper.contexts):
        context.detach()
    with pytest.raises(PitchResolutionError, match="No pitch rule"):
        scene.resolve(Fraction(0))


def test_foreign_staff_and_point_are_refused() -> None:
    scene = build_scene()
    other = build_scene()
    with pytest.raises(ValueError, match="Staff is not"):
        scene.resolve(Fraction(0), staff=other.upper)
    with pytest.raises(UnreachableFrameError):
        scene.pitch.resolve(
            staff=scene.upper,
            point=Point(frame=other.geometry.root, value=Fraction(0)),
            staff_step=0,
            accidental=Accidental.NATURAL,
        )


def test_multiple_clefs_and_touching_octave_lines() -> None:
    scene = build_scene()
    ClefChange.create(start=scene.anchor(Fraction(1)), staff=scene.upper, clef=Clef.BASS)
    ClefChange.create(
        start=scene.anchor(Fraction(2)),
        staff=scene.upper,
        clef=Clef.TREBLE,
        octave_transposition=-1,
    )
    for start, end, shift in [(0, 1, 1), (1, 2, -1), (2, 3, 2)]:
        OctaveTransposition.create(
            start=scene.anchor(Fraction(start)),
            end=scene.anchor(Fraction(end)),
            staff=scene.upper,
            octaves=shift,
        )
    for at, expected in [
        (Fraction(0), 76),
        (Fraction(999, 1000), 76),
        (Fraction(1), 31),
        (Fraction(1999, 1000), 31),
        (Fraction(2), 76),
        (Fraction(3), 52),
    ]:
        assert scene.resolve(Fraction(at)).midi_note == expected


def test_unequal_measure_lengths_and_equivalent_point_frames() -> None:
    scene = build_scene()
    for measure, quarters in zip(scene.document.measures, (3, 5, 2, 4), strict=True):
        measure.set_time_signature(
            time_signature=RhythmicSize(
                value=DottedRhythmicValue(value=RhythmicValue.QUARTER), count=quarters
            )
        )
    scene.geometry.invalidate_measures()
    anchor = TemporalAnchor.create(
        measure=scene.document.measures[1], position=MeasurePosition(value=Fraction(1, 4))
    )
    ClefChange.create(start=anchor, staff=scene.upper, clef=Clef.BASS)
    assert scene.resolve(Fraction(999, 1000)).midi_note == 64
    global_pitch = scene.resolve(Fraction(1))
    local_pitch = scene.pitch.resolve(
        staff=scene.upper,
        point=Point(
            frame=scene.geometry.of_measure(measure=scene.document.measures[1]),
            value=Fraction(1, 4),
        ),
        staff_step=0,
        accidental=Accidental.NATURAL,
    )
    assert local_pitch.midi_note == 43
    assert local_pitch == global_pitch


@pytest.mark.parametrize("at", [Fraction(-1, 1000), Fraction(4), Fraction(4001, 1000)])
def test_score_boundary_queries_are_refused(at: Fraction) -> None:
    scene = build_scene()
    assert scene.resolve(Fraction(0)).midi_note == 64
    assert scene.resolve(Fraction(3999, 1000)).midi_note == 64
    with pytest.raises(PitchResolutionError, match="outside"):
        scene.resolve(at)
