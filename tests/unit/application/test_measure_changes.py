import json
from collections.abc import Callable
from fractions import Fraction
from typing import Any

import pytest
from tests.unit.domain.scene import (
    Score,
    anchor_at,
    build_score,
    delete_entities,
    insert_note,
    note_at,
    quarters,
)

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.application.use_cases.score.shared.measure_changes import (
    MeasureChanges,
    measure_changes,
)
from piano_app.application.use_cases.score.shared.record_patch import diff_records
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    SustainHold,
    TempoChange,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    GlissandoType,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Glissando, Tie
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent
from piano_app.domain.score.document.services.playback import (
    MeasureSounds,
    build_playback_chunks,
)

# An edit, and the edit taken back, must name every measure whose share of the view or whose sound
# changed: a measure left out would stay old on the client.

_CODEC: ScoreDocumentCodec = ScoreDocumentCodec()


def _score() -> Score:
    """Four measures: quarters in the first three, the last empty."""
    score: Score = build_score(measure_count=4)
    for measure in range(3):
        quarters(score=score, measure=measure)

    return score


def _pitch(score: Score) -> None:
    note_at(score=score, at=Fraction(1, 4)).set_staff_step(staff_step=3)


def _accidental(score: Score) -> None:
    note_at(score=score, at=Fraction(1, 2)).set_accidental(accidental=Accidental.SHARP)


def _accent(score: Score) -> None:
    note_at(score=score, at=Fraction(3, 4)).note_carrier.set_articulations(
        articulations=frozenset({Articulation.ACCENT})
    )


def _insert(score: Score) -> None:
    insert_note(score=score, at=Fraction(3), rhythmic_value=RhythmicValue.QUARTER)


def _delete(score: Score) -> None:
    delete_entities(score=score, entity_ids=[note_at(score=score, at=Fraction(5, 4)).id])


def _tie_over_the_barline(score: Score) -> None:
    Tie.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
    )


def _dynamic(score: Score) -> None:
    DynamicChange.create(
        start=anchor_at(score=score, at=Fraction(1)),
        voice=score.voice,
        dynamic=DynamicMarking.FORTE,
    )


def _hairpin(score: Score) -> None:
    Hairpin.create(
        start=anchor_at(score=score, at=Fraction(1, 4)),
        end=anchor_at(score=score, at=Fraction(5, 4)),
        voice=score.voice,
        steps=2,
    )


def _key(score: Score) -> None:
    KeySignatureChange.create(
        start=anchor_at(score=score, at=Fraction(1)),
        staff=score.staff,
        alterations=(Accidental.SHARP,) * 7,
    )


def _clef(score: Score) -> None:
    ClefChange.create(
        start=anchor_at(score=score, at=Fraction(1)), staff=score.staff, clef=Clef.BASS
    )


def _tempo(score: Score) -> None:
    TempoChange.create(
        start=anchor_at(score=score, at=Fraction(1)),
        beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
        bpm=90,
    )


def _pedal(score: Score) -> None:
    SustainHold.create(
        start=anchor_at(score=score, at=Fraction(1, 2)),
        end=anchor_at(score=score, at=Fraction(3, 2)),
    )


def _grace(score: Score) -> None:
    intent = AddGraceNoteIntent(
        host_carrier_id=note_at(score=score, at=Fraction(1, 4)).note_carrier.id,
        placement=GracePlacement.BEFORE,
        grace_type=GraceType.APPOGGIATURA,
        written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
        staff_id=score.staff.id,
        staff_step=2,
        accidental=Accidental.SHARP,
    )
    build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


def _accidental_on_a_tied_note(score: Score) -> None:
    note_at(score=score, at=Fraction(3, 4)).set_accidental(accidental=Accidental.SHARP)


def _glissando(score: Score) -> None:
    Glissando.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
        glissando_type=GlissandoType.STRAIGHT,
    )


def _end_of_a_glissando(score: Score) -> None:
    note_at(score=score, at=Fraction(1)).set_staff_step(staff_step=4)


# what is in the score before an edit, when the edit needs it
_SETUPS: dict[str, Callable[[Score], None]] = {
    "accidental on a tied note": _tie_over_the_barline,
    "end of a glissando": _glissando,
}
_EDITS: dict[str, Callable[[Score], None]] = {
    "pitch": _pitch,
    "accidental": _accidental,
    "accent": _accent,
    "insert": _insert,
    "delete": _delete,
    "tie over the barline": _tie_over_the_barline,
    "dynamic": _dynamic,
    "hairpin": _hairpin,
    "key": _key,
    "clef": _clef,
    "tempo": _tempo,
    "pedal": _pedal,
    "grace note": _grace,
    "accidental on a tied note": _accidental_on_a_tied_note,
    "end of a glissando": _end_of_a_glissando,
}
# edits of notes: what they reach is their own measures, never every measure
_LOCAL: frozenset[str] = frozenset(
    {
        "pitch",
        "accidental",
        "accent",
        "insert",
        "delete",
        "tie over the barline",
        "grace note",
        "accidental on a tied note",
        "end of a glissando",
    }
)


def _state(document: ScoreDocument) -> tuple[dict[str, str], dict[str, MeasureSounds], str]:
    view: ScoreView = ScoreView(document=document)
    content: dict[str, str] = {
        measure.id: json.dumps(view.measure_json(measure=measure), sort_keys=True)
        for measure in document.measures
    }
    sound: dict[str, MeasureSounds] = {
        share.measure_id: share for share in build_playback_chunks(document=document).measures
    }

    return content, sound, json.dumps(view.header_json(), sort_keys=True)


def _predicted_and_seen(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    seen_before: tuple[dict[str, str], dict[str, MeasureSounds], str],
    document: ScoreDocument,
) -> MeasureChanges:
    """What the change from ``before`` to ``after`` is said to reach, checked against what it
    does."""
    predicted: MeasureChanges = measure_changes(
        before=before,
        change=diff_records(before=before, after=after),
        document=document,
        view=ScoreView(document=document),
    )
    content, sound, header = _state(document)
    old_content, old_sound, old_header = seen_before

    drawn: set[str] = {key for key, value in content.items() if old_content.get(key) != value}
    sounding: set[str] = {key for key, value in sound.items() if old_sound.get(key) != value}
    if predicted.content is not None:
        assert drawn <= predicted.content
    if predicted.sound is not None:
        assert sounding <= predicted.sound
    if header != old_header:
        assert predicted.header

    return predicted


@pytest.mark.unit
@pytest.mark.parametrize("name", list(_EDITS))
def test_an_edit_and_the_edit_taken_back_name_every_measure_they_change(name: str) -> None:
    score: Score = _score()
    if name in _SETUPS:
        _SETUPS[name](score)
    before: dict[str, Any] = _CODEC.serialize(score.document)
    seen_before = _state(score.document)

    _EDITS[name](score)
    after: dict[str, Any] = _CODEC.serialize(score.document)
    seen_after = _state(score.document)
    forward: MeasureChanges = _predicted_and_seen(
        before=before, after=after, seen_before=seen_before, document=score.document
    )

    taken_back: ScoreDocument = _CODEC.deserialize(before)
    back: MeasureChanges = _predicted_and_seen(
        before=after, after=before, seen_before=seen_after, document=taken_back
    )

    if name in _LOCAL:
        for reach in (forward, back):
            assert reach.content is not None
            assert reach.sound is not None
            assert len(reach.sound) <= 2


@pytest.mark.unit
def test_a_pitch_reaches_only_its_measure_and_a_key_the_measures_after_it() -> None:
    score: Score = _score()
    before: dict[str, Any] = _CODEC.serialize(score.document)
    first, second, third, fourth = (measure.id for measure in score.document.measures)

    _pitch(score)
    pitch: MeasureChanges = measure_changes(
        before=before,
        change=diff_records(before=before, after=_CODEC.serialize(score.document)),
        document=score.document,
        view=ScoreView(document=score.document),
    )
    assert pitch.sound == {first}

    before = _CODEC.serialize(score.document)
    _key(score)
    key: MeasureChanges = measure_changes(
        before=before,
        change=diff_records(before=before, after=_CODEC.serialize(score.document)),
        document=score.document,
        view=ScoreView(document=score.document),
    )
    assert key.sound == {second, third, fourth}
