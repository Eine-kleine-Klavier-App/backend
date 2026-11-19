from piano_app.domain.score.document.services.playback import (
    PlaybackNote,
    PlaybackPedal,
    PlaybackProjection,
    PlayedAnchor,
    TimelineSegment,
)


def playback_map_payload(*, projection: PlaybackProjection, version: int) -> dict[str, object]:
    """The map of the playback for the frontend. ``notes`` are the notes in the order they
    sound; ``anchors`` the leaves (notes, chords, rests) as they are played, for lighting them;
    ``segments`` the stretches of the score in the order they are played, each with moments
    from which the time of a place of the score is read. With repeats a place of the score is
    played more than once, so the map is by time, with a segment for each pass."""
    return {
        "version": version,
        "extent_ms": projection.extent_ms,
        "notes": [note_payload(note=note) for note in projection.notes],
        "pedals": [pedal_payload(pedal=pedal) for pedal in projection.pedals],
        "anchors": [anchor_payload(anchor=anchor) for anchor in projection.anchors],
        "segments": [segment_payload(segment=segment) for segment in projection.segments],
    }


def note_payload(*, note: PlaybackNote) -> dict[str, object]:
    return {
        "source_id": note.source_id,
        "pitch": note.pitch,
        "start_ms": note.start_ms,
        "key_release_ms": note.key_release_ms,
        "end_ms": note.end_ms,
        "velocity": note.velocity,
    }


def pedal_payload(*, pedal: PlaybackPedal) -> dict[str, object]:
    return {"down_ms": pedal.down_ms, "up_ms": pedal.up_ms}


def anchor_payload(*, anchor: PlayedAnchor) -> dict[str, object]:
    return {
        "carrier_id": anchor.carrier_id,
        "start_ms": anchor.start_ms,
        "end_ms": anchor.end_ms,
    }


def segment_payload(*, segment: TimelineSegment) -> dict[str, object]:
    return {
        "start": {
            "numerator": segment.start.numerator,
            "denominator": segment.start.denominator,
        },
        "end": {"numerator": segment.end.numerator, "denominator": segment.end.denominator},
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "moments": [
            {
                "position": {
                    "numerator": moment.position.numerator,
                    "denominator": moment.position.denominator,
                },
                "time_ms": moment.time_ms,
            }
            for moment in segment.moments
        ],
    }


def preview_carrier_payload(
    *, projection: PlaybackProjection, carrier_id: str, version: int
) -> dict[str, object]:
    return {
        "version": version,
        "carrier_id": carrier_id,
        "notes": [
            {
                "source_id": note.source_id,
                "pitch": note.pitch,
                "velocity": note.velocity,
                "duration_ms": note.key_release_ms - note.start_ms,
            }
            for note in projection.notes
        ],
    }
