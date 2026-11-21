from dataclasses import dataclass
from fractions import Fraction

from piano_app.application.ports.importing import (
    IssueKind,
    SourceMeasure,
    SourceScore,
)
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .lookup import LeafKey, NoteKey, leaf_index, note_index
from .mappings import NOTE_TYPES, midi_of

_QUARTERS_PER_WHOLE: int = 4
_NAMES: tuple[str, ...] = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparisonIssue:
    """One difference between a file and a draft, tied to a measure of the draft."""

    kind: IssueKind
    measure_index: int | None
    """0-based measure of the draft; ``None`` when the difference is not in one measure."""

    onset: Fraction | None
    """Where in the measure, in quarter notes from its start (the start of anything that lasts);
    ``None`` when the difference has no place on a beat."""

    message: str


class ScoreComparer:
    """Compares a source score (read from a file of any format) with a draft's document.

    The notes are matched by voice, staff, measure, position and sounding pitch, so a difference
    in spelling is not one. What the reader could not take from the file is listed as it was
    reported. Marks, ties and grace notes are not compared yet."""

    def compare(
        self, *, document: ScoreDocument, source: SourceScore
    ) -> tuple[ComparisonIssue, ...]:
        found: list[ComparisonIssue] = []
        labels: dict[str, int] = {}
        for index, measure in enumerate(source.measures):
            labels.setdefault(measure.number, index)

        for issue in source.issues:
            found.append(
                ComparisonIssue(
                    kind=issue.kind,
                    measure_index=None if issue.measure is None else labels.get(issue.measure),
                    onset=issue.onset,
                    message=issue.message,
                )
            )

        if len(source.measures) != len(document.measures):
            found.append(
                ComparisonIssue(
                    kind=IssueKind.MISMATCH,
                    measure_index=None,
                    onset=None,
                    message=f"The file has {len(source.measures)} measures, "
                    f"the draft has {len(document.measures)}.",
                )
            )

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
        in_draft: set[NoteKey] = set(note_index(document=document, pitch=pitch))
        leaves: dict[LeafKey, LeafRhythmicContainer] = leaf_index(document=document)
        voice_numbers: list[int] = sorted({n.voice for m in source.measures for n in m.notes})

        expected: set[NoteKey] = set()
        # each note the draft lacks, adds or holds at another length, by measure:
        # its onset in quarters and its name
        missing: dict[int, list[tuple[Fraction, str]]] = {}
        wrong_length: dict[int, list[tuple[Fraction, str]]] = {}
        for index, measure in enumerate(source.measures):
            self._length(document=document, measure=measure, index=index, found=found)
            for note in measure.notes:
                if note.is_grace or note.pitch is None:
                    continue

                key: NoteKey = (
                    voice_numbers.index(note.voice),
                    note.staff - 1,
                    index,
                    note.onset / _QUARTERS_PER_WHOLE,
                    midi_of(pitch=note.pitch),
                )
                expected.add(key)
                if key not in in_draft:
                    missing.setdefault(index, []).append(
                        (note.onset, _name(midi=key[4], onset=note.onset))
                    )
                elif note.tuplet is None and note.written_type in NOTE_TYPES:
                    leaf: LeafRhythmicContainer | None = leaves.get((key[0], key[2], key[3]))
                    notated: Fraction = DottedRhythmicValue(
                        value=NOTE_TYPES[note.written_type], dots_count=note.dots
                    ).fraction
                    if leaf is not None and leaf.written_size.fraction != notated:
                        wrong_length.setdefault(index, []).append(
                            (note.onset, _name(midi=key[4], onset=note.onset))
                        )

        extra: dict[int, list[tuple[Fraction, str]]] = {}
        for key in sorted(in_draft, key=lambda k: (k[2], k[3], k[4])):
            if key not in expected:
                onset: Fraction = key[3] * _QUARTERS_PER_WHOLE
                extra.setdefault(key[2], []).append((onset, _name(midi=key[4], onset=onset)))

        for index in sorted({*missing, *extra, *wrong_length}):
            for notes, text in (
                (missing.get(index), "In the file but not in the draft"),
                (extra.get(index), "In the draft but not in the file"),
                (wrong_length.get(index), "A different length in the draft"),
            ):
                # one entry per note, at its own beat
                for onset, name in notes or []:
                    found.append(
                        ComparisonIssue(
                            kind=IssueKind.MISMATCH,
                            measure_index=index,
                            onset=onset,
                            message=f"{text}: {name}.",
                        )
                    )

        return tuple(found)

    def _length(
        self,
        *,
        document: ScoreDocument,
        measure: SourceMeasure,
        index: int,
        found: list[ComparisonIssue],
    ) -> None:
        if index >= len(document.measures) or measure.is_implicit:
            return

        wanted: Fraction = Fraction(measure.time.beats, measure.time.beat_type)
        if document.measures[index].time_signature.fraction != wanted:
            found.append(
                ComparisonIssue(
                    kind=IssueKind.MISMATCH,
                    measure_index=index,
                    onset=None,
                    message=f"The file's measure is {measure.time.beats}/{measure.time.beat_type}, "
                    f"the draft's is {document.measures[index].time_signature.fraction}.",
                )
            )


def _name(*, midi: int, onset: Fraction) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 1} at {_beat(onset=onset)}"


def _beat(*, onset: Fraction) -> str:
    """Where a note starts, counted from beat 1 of its measure."""
    beat: Fraction = onset + 1
    whole: int = beat.numerator // beat.denominator
    rest: Fraction = beat - whole
    if rest == 0:
        return f"beat {whole}"

    return f"beat {whole} {rest}" if whole else f"beat {rest}"
