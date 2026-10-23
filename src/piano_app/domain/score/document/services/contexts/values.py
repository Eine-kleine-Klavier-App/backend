from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.context import (
    Context,
    DynamicChange,
    Hairpin,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, DynamicMarking
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .index import ContextIndex
from .scope import Scope

# at one position a gradual change that ends there is over before a point there takes over,
# and one that starts there starts from what a point there says
_ENDS: int = 0
_POINT: int = 1
_STARTS: int = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class Tempo:
    """``bpm`` beats of ``beat`` per minute; a gradual change can leave it fractional."""

    beat: DottedRhythmicValue
    bpm: Fraction


class ContextValues:
    """Reads the tempo and the dynamic in force at a place, from the points and the gradual
    changes of the score.

    A point sets the value from its position on. A gradual change starts from the value in
    force at its start and ends at a value derived from it — a tempo transition at its ratio
    of speed, a hairpin at its number of dynamic levels, held to the scale — and that value
    stays until the next point. Inside a gradual change the value in force is the one it
    starts from. So editing a point moves every gradual change after it, up to the next
    point.

    Read through the context index and the geometry it is given and holding nothing of its
    own, so it answers for the score as they do. Positions are on the global timeline.
    """

    def __init__(self, *, contexts: ContextIndex, geometry: ScoreGeometry) -> None:
        self._contexts: ContextIndex = contexts
        self._geometry: ScoreGeometry = geometry

    def tempo_at(self, *, at: Fraction) -> Tempo:
        """The tempo in force at ``at``: a tempo change there counts, a transition that ends
        there is over."""
        return self._walk_tempo(until=at, transition=None)[0]

    def transition_start_tempo(self, *, transition: TempoTransition) -> Tempo:
        """The tempo a transition starts from."""
        start: Tempo | None = self._walk_tempo(until=None, transition=transition)[1]
        if start is None:
            raise ValueError("The transition is not in the score.")

        return start

    def transition_end_tempo(self, *, transition: TempoTransition) -> Tempo:
        """The tempo a transition ends at."""
        end: Tempo | None = self._walk_tempo(until=None, transition=transition)[2]
        if end is None:
            raise ValueError("The transition is not in the score.")

        return end

    def dynamic_at(self, *, voice: Voice, at: Fraction) -> DynamicMarking:
        """The dynamic of ``voice`` in force at ``at``."""
        return self._walk_dynamic(voice=voice, until=at, hairpin=None)[0]

    def hairpin_start_dynamic(self, *, hairpin: Hairpin, voice: Voice) -> DynamicMarking:
        """The dynamic ``voice`` starts from under ``hairpin``, which must name it."""
        start: DynamicMarking | None = self._walk_dynamic(voice=voice, until=None, hairpin=hairpin)[
            1
        ]
        if start is None:
            raise ValueError("The hairpin does not name this voice.")

        return start

    def hairpin_end_dynamic(self, *, hairpin: Hairpin, voice: Voice) -> DynamicMarking:
        """The dynamic ``voice`` ends at under ``hairpin``, which must name it."""
        end: DynamicMarking | None = self._walk_dynamic(voice=voice, until=None, hairpin=hairpin)[2]
        if end is None:
            raise ValueError("The hairpin does not name this voice.")

        return end

    def _walk_tempo(
        self,
        *,
        until: Fraction | None,
        transition: TempoTransition | None,
    ) -> tuple[Tempo, Tempo | None, Tempo | None]:
        """The tempo after every event up to ``until`` (all of them if None), and where
        ``transition`` starts and ends."""
        events: list[tuple[Fraction, int, Context]] = []
        for point in self._contexts.contexts_of(kind=TempoChange, scope=Scope.score()):
            events.append((self._geometry.point_of(anchor=point.start).value, _POINT, point))

        for transition_context in self._contexts.contexts_of(
            kind=TempoTransition, scope=Scope.score()
        ):
            events.append(
                (
                    self._geometry.point_of(anchor=transition_context.start).value,
                    _STARTS,
                    transition_context,
                )
            )
            events.append(
                (
                    self._geometry.end_of(context=transition_context).value,
                    _ENDS,
                    transition_context,
                )
            )

        events.sort(key=lambda event: (event[0], event[1]))

        state: Tempo | None = None
        started: dict[Context, Tempo] = {}
        start_of_transition: Tempo | None = None
        end_of_transition: Tempo | None = None
        for position, order, context in events:
            if until is not None and position > until:
                break

            if isinstance(context, TempoChange):
                state = Tempo(beat=context.beat, bpm=Fraction(context.bpm))
            elif state is None:
                raise ValueError("No tempo is in force before a tempo transition.")
            elif order == _STARTS:
                started[context] = state
                if context is transition:
                    start_of_transition = state
            elif isinstance(context, TempoTransition):
                origin: Tempo = started[context]
                state = Tempo(beat=origin.beat, bpm=origin.bpm * context.ratio)
                if context is transition:
                    end_of_transition = state

        if state is None:
            raise ValueError("No tempo is in force.")

        return state, start_of_transition, end_of_transition

    def _walk_dynamic(
        self,
        *,
        voice: Voice,
        until: Fraction | None,
        hairpin: Hairpin | None,
    ) -> tuple[DynamicMarking, DynamicMarking | None, DynamicMarking | None]:
        """The dynamic of ``voice`` after every event up to ``until`` (all of them if None),
        and where ``hairpin`` starts and ends."""
        scope: Scope = Scope.of_voice(voice=voice)
        events: list[tuple[Fraction, int, Context]] = []
        for point in self._contexts.contexts_of(kind=DynamicChange, scope=scope):
            events.append((self._geometry.point_of(anchor=point.start).value, _POINT, point))

        for gradual in self._contexts.contexts_of(kind=Hairpin, scope=scope):
            events.append((self._geometry.point_of(anchor=gradual.start).value, _STARTS, gradual))
            events.append((self._geometry.end_of(context=gradual).value, _ENDS, gradual))

        events.sort(key=lambda event: (event[0], event[1]))

        state: DynamicMarking | None = None
        started: dict[Context, DynamicMarking] = {}
        start_of_hairpin: DynamicMarking | None = None
        end_of_hairpin: DynamicMarking | None = None
        for position, order, context in events:
            if until is not None and position > until:
                break

            if isinstance(context, DynamicChange):
                state = context.dynamic
            elif state is None:
                raise ValueError("No dynamic is in force before a hairpin.")
            elif order == _STARTS:
                started[context] = state
                if context is hairpin:
                    start_of_hairpin = state
            elif isinstance(context, Hairpin):
                state = DynamicMarking.at_level(started[context].level + context.steps)
                if context is hairpin:
                    end_of_hairpin = state

        if state is None:
            raise ValueError("No dynamic is in force.")

        return state, start_of_hairpin, end_of_hairpin
