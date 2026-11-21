"""The score sent by measure: the draft read and every edit answer with the measures that changed
and their sound."""

from piano_app.application.use_cases.score.shared import MeasureSync
from piano_app.domain.score.document.services.playback import MeasureSounds, PlaybackChunks

from .playback.responses import anchor_payload, note_payload, pedal_payload, segment_payload


def measure_sync_payload(*, sync: MeasureSync) -> dict[str, object]:
    """The measures a client is sent: ``from_version`` null is the whole score; a client holding
    another version than ``from_version`` takes the whole score again."""
    return {
        "from_version": sync.from_version,
        "to_version": sync.to_version,
        "header": sync.header,
        "measures": list(sync.measures),
        "sounds": [_sounds_payload(sounds=sounds) for sounds in sync.sounds],
        "timing": None if sync.timing is None else _timing_payload(chunks=sync.timing),
        "removed": list(sync.removed),
        "sound_error": sync.sound_error,
    }


def _sounds_payload(*, sounds: MeasureSounds) -> dict[str, object]:
    return {
        "measure_id": sounds.measure_id,
        "strikes": [
            {"note_id": strike.note_id, "pitch": strike.pitch, "velocity": strike.velocity}
            for strike in sounds.strikes
        ],
        "notes": [note_payload(note=note) for note in sounds.notes],
        "anchors": [anchor_payload(anchor=anchor) for anchor in sounds.anchors],
    }


def _timing_payload(*, chunks: PlaybackChunks) -> dict[str, object]:
    return {
        "extent_ms": chunks.extent_ms,
        "pedals": [pedal_payload(pedal=pedal) for pedal in chunks.pedals],
        "segments": [segment_payload(segment=segment) for segment in chunks.segments],
    }
