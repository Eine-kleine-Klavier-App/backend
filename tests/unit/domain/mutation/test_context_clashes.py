"""Moving the start or the end of a context meets the same clashes as creating it; creating at
a taken place displaces by the policy of the kind."""

from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    OctaveTransposition,
    Slur,
    SpanContext,
    SustainHold,
    TempoChange,
    TempoTransition,
    VoiceScoped,
)
from piano_app.domain.score.document.models.notation import (
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff, Voice
from piano_app.domain.score.document.services.mutation import MutationEngine
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateDynamicChangeRequest,
    CreateHairpinRequest,
    CreateKeySignatureChangeRequest,
    CreateOctaveTranspositionRequest,
    CreateSlurRequest,
    CreateSustainHoldRequest,
    CreateTempoChangeRequest,
    CreateTempoTransitionRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
)

from ..scene import build_engine


def _at(beat: int) -> MeasurePosition:
    return MeasurePosition.of(numerator=beat, denominator=4)


@dataclass(slots=True)
class _World:
    """One measure of four beats, one staff, two voices; contexts are placed by beat, voices
    by their index."""

    measure: Measure
    staff: Staff
    voices: list[Voice]
    document: ScoreDocument
    engine: MutationEngine

    @classmethod
    def create(cls) -> _World:
        measure: Measure = Measure.create()
        staff: Staff = Staff()
        voices: list[Voice] = [Voice(), Voice()]
        return cls(
            measure=measure,
            staff=staff,
            voices=voices,
            document=ScoreDocument.create(voices=voices, staffs=[staff], measures=[measure]),
            engine=build_engine(),
        )

    def process(self, request: MutationRequest) -> None:
        self.engine.process(document=self.document, requests=[request])

    def contexts(self, kind: type[Context]) -> list[Context]:
        return [
            context
            for anchor in self.measure.anchors
            for context in anchor.starting_contexts
            if type(context) is kind
        ]

    def snapshot(self) -> list[tuple[str, Fraction, Fraction | None, tuple[int, ...]]]:
        """Every context with its place and voices, to see that a refusal changed nothing."""
        return [
            (
                type(context).__name__,
                context.start.position.value,
                context.end.position.value if isinstance(context, SpanContext) else None,
                (self.voices.index(context.voice),) if isinstance(context, VoiceScoped) else (),
            )
            for anchor in self.measure.anchors
            for context in anchor.starting_contexts
        ]

    def octave(self, start: int, end: int) -> None:
        self.process(
            CreateOctaveTranspositionRequest(
                start_measure=self.measure,
                start_position=_at(start),
                end_measure=self.measure,
                end_position=_at(end),
                staff=self.staff,
                octaves=1,
            )
        )

    def hairpin(self, start: int, end: int, voices: tuple[int, ...]) -> None:
        for index in voices:
            self.process(
                CreateHairpinRequest(
                    start_measure=self.measure,
                    start_position=_at(start),
                    end_measure=self.measure,
                    end_position=_at(end),
                    voice=self.voices[index],
                    steps=1,
                )
            )

    def transition(self, start: int, end: int) -> None:
        self.process(
            CreateTempoTransitionRequest(
                start_measure=self.measure,
                start_position=_at(start),
                end_measure=self.measure,
                end_position=_at(end),
                ratio=Fraction(2),
            )
        )

    def sustain(self, start: int, end: int) -> None:
        self.process(
            CreateSustainHoldRequest(
                start_measure=self.measure,
                start_position=_at(start),
                end_measure=self.measure,
                end_position=_at(end),
            )
        )

    def slur(self, start: int, end: int, voices: tuple[int, ...]) -> None:
        for index in voices:
            self.process(
                CreateSlurRequest(
                    start_measure=self.measure,
                    start_position=_at(start),
                    end_measure=self.measure,
                    end_position=_at(end),
                    voice=self.voices[index],
                )
            )

    def dynamic(self, beat: int, voices: tuple[int, ...]) -> None:
        for index in voices:
            self.process(
                CreateDynamicChangeRequest(
                    measure=self.measure,
                    position=_at(beat),
                    voice=self.voices[index],
                    dynamic=DynamicMarking.FORTE,
                )
            )

    def tempo(self, beat: int, bpm: int = 100) -> None:
        self.process(
            CreateTempoChangeRequest(
                measure=self.measure,
                position=_at(beat),
                beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
                bpm=bpm,
            )
        )

    def clef(self, beat: int) -> None:
        self.process(
            CreateClefChangeRequest(
                measure=self.measure, position=_at(beat), staff=self.staff, clef=Clef.BASS
            )
        )

    def key(self, beat: int) -> None:
        self.process(
            CreateKeySignatureChangeRequest(
                measure=self.measure, position=_at(beat), staff=self.staff
            )
        )

    def request(self, action: tuple[object, ...]) -> MutationRequest:
        """The edit an action names: ``("start", kind, n, beat)`` or ``("end", kind, n, beat)``,
        on the n-th context of that kind."""
        verb, kind, index, argument = action
        assert isinstance(kind, type) and issubclass(kind, Context)
        assert isinstance(index, int)
        target: Context = self.contexts(kind)[index]
        if verb == "start":
            assert isinstance(argument, int)
            return UpdateContextStartRequest(
                target=target, measure=self.measure, position=_at(argument)
            )

        assert verb == "end"
        assert isinstance(argument, int) and isinstance(target, SpanContext)
        return UpdateContextEndRequest(target=target, measure=self.measure, position=_at(argument))


_OVERLAP: str = "cannot overlap another"
_SAME_PLACE: str = "Another context of the same kind already starts there"

# (what stands before, the edit, the refusal it meets or None when it is allowed)
_CASES: list[tuple[list[tuple[object, ...]], tuple[object, ...], str | None]] = [
    # a span's start or end moves over a span of its own kind
    ([("octave", 0, 1), ("octave", 2, 3)], ("start", OctaveTransposition, 1, 0), _OVERLAP),
    ([("octave", 0, 1), ("octave", 2, 3)], ("end", OctaveTransposition, 0, 3), _OVERLAP),
    (
        [("hairpin", 0, 1, (0,)), ("hairpin", 2, 3, (0,))],
        ("start", Hairpin, 1, 0),
        _OVERLAP,
    ),
    ([("hairpin", 0, 1, (0,)), ("hairpin", 2, 3, (0,))], ("end", Hairpin, 0, 3), _OVERLAP),
    ([("hairpin", 0, 1, (0,)), ("hairpin", 2, 3, (1,))], ("end", Hairpin, 0, 3), None),
    ([("transition", 0, 1), ("transition", 2, 3)], ("start", TempoTransition, 1, 0), _OVERLAP),
    ([("transition", 0, 1), ("transition", 2, 3)], ("end", TempoTransition, 0, 3), _OVERLAP),
    ([("slur", 0, 1, (0,)), ("slur", 2, 3, (0,))], ("end", Slur, 0, 3), None),
    ([("sustain", 0, 1), ("sustain", 2, 3)], ("start", SustainHold, 1, 0), _OVERLAP),
    ([("sustain", 0, 1), ("sustain", 2, 3)], ("end", SustainHold, 0, 3), _OVERLAP),
    ([("sustain", 0, 1), ("sustain", 1, 3)], ("end", SustainHold, 0, 1), None),
    # a span grows over a partner, a partner point moves into a span
    (
        [("hairpin", 0, 1, (0,)), ("dynamic", 2, (0,))],
        ("end", Hairpin, 0, 3),
        "cannot hold a DynamicChange strictly inside",
    ),
    (
        [("transition", 0, 1), ("tempo", 2)],
        ("end", TempoTransition, 0, 3),
        "cannot hold a TempoChange strictly inside",
    ),
    (
        [("hairpin", 0, 3, (0,)), ("dynamic", 3, (0,))],
        ("start", DynamicChange, 0, 1),
        "cannot be placed inside a Hairpin",
    ),
    (
        [("transition", 0, 3), ("tempo", 3)],
        ("start", TempoChange, 0, 1),
        "cannot be placed inside a TempoTransition",
    ),
    # a point moves onto a place its kind already holds
    ([("clef", 0), ("clef", 2)], ("start", ClefChange, 1, 0), _SAME_PLACE),
    ([("key", 0), ("key", 2)], ("start", KeySignatureChange, 1, 0), _SAME_PLACE),
    ([("tempo", 0), ("tempo", 2)], ("start", TempoChange, 1, 0), _SAME_PLACE),
    ([("dynamic", 0, (0,)), ("dynamic", 2, (0,))], ("start", DynamicChange, 1, 0), _SAME_PLACE),
    # the voices have their own contexts: one voice's context does not meet another voice's
    ([("hairpin", 0, 2, (0,)), ("hairpin", 0, 2, (1,))], ("end", Hairpin, 1, 3), None),
    ([("dynamic", 1, (0,)), ("dynamic", 2, (1,))], ("start", DynamicChange, 1, 1), None),
    ([("hairpin", 0, 3, (1,)), ("dynamic", 1, (0,))], ("start", DynamicChange, 0, 2), None),
]


@pytest.mark.unit
@pytest.mark.parametrize(("stands", "edit", "refusal"), _CASES)
def test_an_edit_meets_the_clashes_creation_meets(
    stands: list[tuple[object, ...]],
    edit: tuple[object, ...],
    refusal: str | None,
) -> None:
    world: _World = _World.create()
    for name, *arguments in stands:
        assert isinstance(name, str)
        getattr(world, name)(*arguments)

    before = world.snapshot()
    request: MutationRequest = world.request(edit)

    if refusal is None:
        world.process(request)
        return

    with pytest.raises(MutationRejectedError, match=refusal):
        world.process(request)

    assert world.snapshot() == before


@pytest.mark.unit
def test_a_dynamic_created_over_one_of_the_same_voice_replaces_it_and_leaves_the_other_voice() -> (
    None
):
    world: _World = _World.create()
    world.dynamic(1, (0, 1))

    world.dynamic(1, (0,))

    assert sorted(world.snapshot()) == sorted(
        [
            ("DynamicChange", Fraction(1, 4), None, (1,)),
            ("DynamicChange", Fraction(1, 4), None, (0,)),
        ]
    )


@pytest.mark.unit
def test_a_tempo_created_at_a_taken_place_replaces_the_old_one() -> None:
    world: _World = _World.create()
    world.tempo(1, bpm=100)

    world.tempo(1, bpm=140)

    (tempo,) = world.contexts(TempoChange)
    assert isinstance(tempo, TempoChange)
    assert tempo.bpm == 140
