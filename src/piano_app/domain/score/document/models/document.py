from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import uuid4

from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    KeySignatureChange,
    TempoChange,
)
from piano_app.domain.score.document.models.notation import (
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    Staff,
    TemporalAnchor,
    Voice,
)

from .mutation_sink import DIRECT_SINK, MutationSink
from .presentation import Presentation

# what a new score starts with at its very start
_INITIAL_TEMPO_BEAT: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)
_INITIAL_BPM: int = 90
_INITIAL_DYNAMIC: DynamicMarking = DynamicMarking.PIANO


@dataclass(slots=True, kw_only=True, eq=False)
class ScoreDocument:
    # staffs and voices are fixed at construction → plain fields
    # behind read-only views. measures is the linked chain the document
    # mutates through append/insert/remove → private + read-only view.
    _voices: list[Voice]
    _staffs: list[Staff]
    _measures: list[Measure]
    _presentation: Presentation = field(default_factory=Presentation)
    _music_revision: str = field(default_factory=lambda: str(uuid4()))

    @property
    def presentation(self) -> Presentation:
        return self._presentation

    @property
    def music_revision(self) -> str:
        return self._music_revision

    def set_music_revision(self, *, revision: str, sink: MutationSink = DIRECT_SINK) -> None:
        sink.set_field(self, "_music_revision", revision)

    def renew_music_revision(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.set_music_revision(revision=str(uuid4()), sink=sink)

    @property
    def voices(self) -> Sequence[Voice]:
        return self._voices

    @property
    def staffs(self) -> Sequence[Staff]:
        return self._staffs

    @property
    def measures(self) -> Sequence[Measure]:
        return self._measures

    @classmethod
    def create(
        cls,
        *,
        voices: list[Voice],
        staffs: list[Staff],
        measures: list[Measure],
    ) -> ScoreDocument:
        document: ScoreDocument = cls(_voices=voices, _staffs=staffs, _measures=[])
        for measure in measures:
            document.append_measure(measure=measure)

        return document

    @classmethod
    def create_fresh(
        cls,
        *,
        voice_count: int,
        staff_count: int,
        measure_count: int,
    ) -> ScoreDocument:
        """A new score, the single entry that makes one: its voices, staffs and measures, and
        the contexts every score always holds at its very start — a clef and a key signature
        on each staff (treble on the first, bass on the others), a dynamic on each voice and
        a tempo for the score.
        """
        if min(voice_count, staff_count, measure_count) < 1:
            raise ValueError("A score needs at least one voice, one staff and one measure.")

        document: ScoreDocument = cls.create(
            voices=[Voice() for _ in range(voice_count)],
            staffs=[Staff() for _ in range(staff_count)],
            measures=[Measure.create() for _ in range(measure_count)],
        )
        document.place_start_contexts()

        return document

    def place_start_contexts(self) -> None:
        """Give the score the contexts it always holds at its very start: a clef and a key
        signature on each staff (treble on the first, bass on the others), a dynamic on each
        voice and a tempo for the score. For a score still being assembled from its parts; a
        new one gets them from ``create_fresh``."""
        start: TemporalAnchor = TemporalAnchor.create(
            measure=self._measures[0], position=MEASURE_START
        )
        TempoChange.create(start=start, beat=_INITIAL_TEMPO_BEAT, bpm=_INITIAL_BPM)
        for index, staff in enumerate(self._staffs):
            ClefChange.create(
                start=start, staff=staff, clef=Clef.TREBLE if index == 0 else Clef.BASS
            )
            KeySignatureChange.create(start=start, staff=staff)

        for voice in self._voices:
            DynamicChange.create(start=start, voice=voice, dynamic=_INITIAL_DYNAMIC)

    def missing_initial_contexts(self) -> list[str]:
        """What the very start of the score lacks of the contexts it must always hold; empty
        when the invariant holds."""
        start: TemporalAnchor | None = None
        if self._measures:
            start = next(
                (
                    anchor
                    for anchor in self._measures[0].anchors
                    if anchor.position == MEASURE_START
                ),
                None,
            )

        starting: Sequence[Context] = [] if start is None else start.starting_contexts

        missing: list[str] = []
        if not any(isinstance(context, TempoChange) for context in starting):
            missing.append("tempo")

        for staff in self._staffs:
            for kind, name in ((ClefChange, "clef"), (KeySignatureChange, "key signature")):
                if not any(
                    isinstance(context, kind) and context.staff is staff for context in starting
                ):
                    missing.append(f"{name} of staff {staff.id}")

        for voice in self._voices:
            if not any(
                isinstance(context, DynamicChange) and context.voice is voice
                for context in starting
            ):
                missing.append(f"dynamic of voice {voice.id}")

        return missing

    def insert_measure_after(
        self,
        *,
        measure: Measure,
        after: Measure,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        # guard from working with a measure that is not in the document
        if after not in self._measures:
            raise ValueError("Measure to insert after is not in the document.")

        # idempotency
        if measure in self._measures:
            return

        # not in this document, but already in a chain, disallow
        if measure.next_measure is not None or measure.prev_measure is not None:
            raise ValueError("Measure is already in a chain.")

        self._link_between(measure=measure, prev=after, nxt=after.next_measure, sink=sink)

        # safe because after is in the document at that point
        index: int = self._measures.index(after)
        sink.list_insert(self, "_measures", index + 1, measure)

    def insert_measure_before(
        self,
        *,
        measure: Measure,
        before: Measure,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        # guard from working with a measure that is not in the document
        if before not in self._measures:
            raise ValueError("Measure to insert before is not in the document.")

        # idempotency
        if measure in self._measures:
            return

        # not in this document, but already in a chain, disallow
        if measure.next_measure is not None or measure.prev_measure is not None:
            raise ValueError("Measure is already in a chain.")

        self._link_between(measure=measure, prev=before.prev_measure, nxt=before, sink=sink)

        # safe because before is in the document at that point
        index: int = self._measures.index(before)
        sink.list_insert(self, "_measures", index, measure)

    def append_measure(
        self,
        *,
        measure: Measure,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        # idempotency
        if measure in self._measures:
            return

        # not in this document, but already in a chain, disallow
        if measure.next_measure is not None or measure.prev_measure is not None:
            raise ValueError("Measure is already in a chain.")

        # lookup current last measure or None
        last: Measure | None = self._measures[-1] if self._measures else None
        self._link_between(measure=measure, prev=last, nxt=None, sink=sink)

        sink.list_append(self, "_measures", measure)

    def remove_measure(
        self,
        *,
        measure: Measure,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        # idempotency
        if measure not in self._measures:
            return

        self._remove_from_chain(measure=measure, sink=sink)

        sink.list_remove(self, "_measures", measure)

    # inserts a measure into the chain, linking it to the previous and next measures
    # no checks of belonging to the document are performed because the method is private
    def _link_between(
        self,
        *,
        measure: Measure,
        prev: Measure | None,
        nxt: Measure | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        measure.set_prev(prev_measure=prev, sink=sink)
        measure.set_next(next_measure=nxt, sink=sink)

        if prev is not None:
            prev.set_next(next_measure=measure, sink=sink)

        if nxt is not None:
            nxt.set_prev(prev_measure=measure, sink=sink)

    # removes a measure from the chain, linking the previous and next measures to each other
    # no checks of belonging to the document are performed because the method is private
    def _remove_from_chain(
        self,
        *,
        measure: Measure,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        prev: Measure | None = measure.prev_measure
        nxt: Measure | None = measure.next_measure

        if prev is not None:
            prev.set_next(next_measure=nxt, sink=sink)

        if nxt is not None:
            nxt.set_prev(prev_measure=prev, sink=sink)

        measure.set_prev(prev_measure=None, sink=sink)
        measure.set_next(next_measure=None, sink=sink)
