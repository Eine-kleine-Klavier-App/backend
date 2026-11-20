"""What a client is sent of a score, measure by measure.

A score loaded as it is goes whole: the header, every measure's share of the view and every
measure's sound. A score after an edit goes as the measures the edit changed (see
``measure_changes``), with the versions of the draft before and after it, so a client that holds
the version before applies it and any other takes the whole score again. Sound that cannot be
worked out (a note outside MIDI, a route that does not end) does not stop the edit: the sync says
so and carries no sound.
"""

from dataclasses import dataclass

from piano_app.application.ports.score import RecordStep
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.services.pitch import PitchResolutionError
from piano_app.domain.score.document.services.playback import (
    MeasureSounds,
    PlaybackChunks,
    build_measure_sounds,
    build_playback_chunks,
)

from .measure_changes import MeasureChanges, measure_changes
from .view import ScoreView


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoreState:
    """A score at one version of its draft, with the step of the record that led to it: None
    when it was loaded as it is; a request that changed nothing has a step with no change."""

    document: ScoreDocument
    view: ScoreView
    version: int
    step: RecordStep | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureSync:
    """What a client is sent: ``from_version`` None is the whole score. ``timing`` (the length,
    the pedal and the segments of the route) comes when the sound of every measure was worked
    out again, ``header`` when what belongs to no one measure changed."""

    from_version: int | None
    to_version: int
    header: dict[str, object] | None
    measures: tuple[dict[str, object], ...]
    sounds: tuple[MeasureSounds, ...]
    timing: PlaybackChunks | None
    removed: tuple[str, ...]
    sound_error: str | None


def state_sync(*, state: ScoreState) -> MeasureSync:
    """The measures a client is sent for ``state``."""
    if state.step is None:
        return _whole(state=state)

    step: RecordStep = state.step
    changes: MeasureChanges = measure_changes(
        before=step.before, change=step.change, document=state.document, view=state.view
    )
    present: list[str] = [measure.id for measure in state.document.measures]
    kept: set[str] = set(present)
    removed: tuple[str, ...] = tuple(
        measure_id for measure_id in step.before.get("measure_ids", []) if measure_id not in kept
    )

    measures: tuple[dict[str, object], ...] = tuple(
        state.view.measure_json(measure=measure)
        for measure in state.document.measures
        if changes.content is None or measure.id in changes.content
    )

    sounds: tuple[MeasureSounds, ...] = ()
    timing: PlaybackChunks | None = None
    sound_error: str | None = None
    try:
        if changes.sound is None:
            timing = build_playback_chunks(document=state.document)
            sounds = timing.measures
        else:
            sounds = build_measure_sounds(
                document=state.document,
                measure_ids=[measure_id for measure_id in present if measure_id in changes.sound],
            )
    except (ValueError, PitchResolutionError) as error:
        sound_error = str(error)

    return MeasureSync(
        from_version=step.from_version,
        to_version=step.to_version,
        header=state.view.header_json() if changes.header or changes.content is None else None,
        measures=measures,
        sounds=sounds,
        timing=timing,
        removed=removed,
        sound_error=sound_error,
    )


def _whole(*, state: ScoreState) -> MeasureSync:
    """The whole score, as it is at its version."""
    timing: PlaybackChunks | None = None
    sound_error: str | None = None
    try:
        timing = build_playback_chunks(document=state.document)
    except (ValueError, PitchResolutionError) as error:
        sound_error = str(error)

    return MeasureSync(
        from_version=None,
        to_version=state.version,
        header=state.view.header_json(),
        measures=tuple(
            state.view.measure_json(measure=measure) for measure in state.document.measures
        ),
        sounds=() if timing is None else timing.measures,
        timing=timing,
        removed=(),
        sound_error=sound_error,
    )
