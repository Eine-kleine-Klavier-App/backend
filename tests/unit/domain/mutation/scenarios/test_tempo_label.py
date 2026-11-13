from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import TempoChange
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    RhythmicValue,
    TempoMarking,
)
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff, Voice
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler.intents import SetTempoIntent


@pytest.mark.parametrize(
    "bpm, word",
    [
        (1, "grave"),
        (39, "grave"),
        (40, "largo"),
        (62, "largo"),
        (63, "adagio"),
        (75, "adagio"),
        (76, "andante"),
        (107, "andante"),
        (108, "moderato"),
        (119, "moderato"),
        (120, "allegro"),
        (161, "allegro"),
        (162, "presto"),
        (900, "presto"),
    ],
)
def test_tempo_range_boundaries(bpm: int, word: str) -> None:
    assert TempoMarking.for_bpm(quarter_bpm=Fraction(bpm)).value == word


def test_tempo_label_recomputes_from_numeric_tempo_and_dotted_beat() -> None:
    document = ScoreDocument.create(
        voices=[Voice()], staffs=[Staff(), Staff()], measures=[Measure.create()]
    )
    compiler, engine = build_compiler(), build_engine()
    for bpm, value, dots, visible, expected in [
        (90, RhythmicValue.QUARTER, 0, True, TempoMarking.ANDANTE),
        (140, RhythmicValue.QUARTER, 0, True, TempoMarking.ALLEGRO),
        (96, RhythmicValue.EIGHTH, 1, True, TempoMarking.ADAGIO),
        (96, RhythmicValue.EIGHTH, 1, False, None),
    ]:
        requests = compiler.compile(
            document=document,
            intent=SetTempoIntent(
                measure_id=document.measures[0].id,
                position=MeasurePosition.of(numerator=0, denominator=1),
                beat=DottedRhythmicValue(value=value, dots_count=dots),
                bpm=bpm,
                show_label=visible,
            ),
        )
        engine.process(document=document, requests=requests)
        tempo = next(
            c
            for c in document.measures[0].anchors[0].starting_contexts
            if isinstance(c, TempoChange)
        )
        assert tempo.label == expected
        assert tempo.show_label is visible
