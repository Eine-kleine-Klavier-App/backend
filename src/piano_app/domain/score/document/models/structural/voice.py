from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.base import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.context.scope.voice import VoiceScoped
    from piano_app.domain.score.document.models.structural.rhythm.metric import (
        RhythmicContainer,
    )


@dataclass(slots=True, kw_only=True, eq=False)
class Voice(ScoreEntity):
    # may be empty at any time
    _children: list[RhythmicContainer] = field(default_factory=list)
    # one-to-many with contexts: a context names one voice, and one voice can be named by
    # several contexts over time
    _contexts: list[VoiceScoped] = field(default_factory=list)

    # no constraint on emptiness in voice
    @property
    def children(self) -> Sequence[RhythmicContainer]:
        return self._children

    @property
    def contexts(self) -> Sequence[VoiceScoped]:
        return self._contexts

    def add_child(
        self,
        *,
        child: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if child.parent is not self:
            # or is not top level
            raise ValueError("Cannot add rhythmic container that belongs to another voice.")

        if child in self._children:
            return

        # ordered insertion: the children are in order, so those before the new one are the first
        # ones and its place is found by halving the list
        low: int = 0
        high: int = len(self._children)
        while low < high:
            middle: int = (low + high) // 2
            if self._children[middle].precedes(child):
                low = middle + 1
            else:
                high = middle

        index: int = low

        sink.list_insert(self, "_children", index, child)

    def remove_child(
        self,
        *,
        child: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if child.parent is not self:
            # or is not top level
            raise ValueError("Cannot remove rhythmic container that belongs to another voice.")

        if child not in self._children:
            return

        sink.list_remove(self, "_children", child)

    def add_context(
        self,
        *,
        context: VoiceScoped,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.voice is not self:
            raise ValueError("Cannot add context that does not name this voice.")

        if context in self._contexts:
            return

        # ordered insertion: the contexts are in order, so those before the new one are the first
        # ones and its place is found by halving the list
        low: int = 0
        high: int = len(self._contexts)
        while low < high:
            middle: int = (low + high) // 2
            if self._contexts[middle].precedes(context):
                low = middle + 1
            else:
                high = middle

        index: int = low

        sink.list_insert(self, "_contexts", index, context)

    def remove_context(
        self,
        *,
        context: VoiceScoped,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.voice is not self:
            raise ValueError("Cannot remove context that does not name this voice.")

        if context not in self._contexts:
            return

        sink.list_remove(self, "_contexts", context)
