from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure, Voice
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from .base import MutatedStatePostprocessor
from .content import holds_content


class EmptyGroupsPostprocessor(MutatedStatePostprocessor):
    """Removes a group left without children where its voice holds nothing else in the
    measures the group reaches — an empty group may not stand in an empty voice or an
    empty measure. A childless group with other content of its voice around stays, and
    the fill tiles it.

    Runs once the leaves without content are gone, so every leaf left is content: a group
    reaching no measure that holds a note or a rest of its voice holds only groups judged
    the same way, which is the bottom-up repeat in one step. Only the outermost such group
    is deleted; its cascade takes the groups inside it.
    """

    def search_fixes(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
    ) -> Sequence[DeleteRequest]:
        fixes: list[DeleteRequest] = []
        for voice in document.voices:
            # the measures where the voice holds a note or a rest, read from what of it
            # reaches into each measure: a group counts only through its own leaves there
            awake: set[Measure] = set()
            for measure in document.measures:
                scopes: list[Voice | GroupRhythmicContainer] = [voice]
                while scopes and measure not in awake:
                    for child, _ in geometry.contents_in(scope=scopes.pop(), measure=measure):
                        if isinstance(child, GroupRhythmicContainer):
                            scopes.append(child)
                        elif holds_content(container=child):
                            awake.add(measure)

            pending: list[Voice | GroupRhythmicContainer] = [voice]
            while pending:
                scope: Voice | GroupRhythmicContainer = pending.pop()
                for child in scope.children:
                    if not isinstance(child, GroupRhythmicContainer):
                        continue

                    # the measures the group reaches, from the one it starts in
                    reach: Span = geometry.global_span_of(container=child)
                    reaches_awake: bool = False
                    reached: Measure | None = child.start_anchor.measure
                    while reached is not None and not reaches_awake:
                        if not geometry.measure_span(measure=reached).intersects(reach):
                            break
                        reaches_awake = reached in awake
                        reached = reached.next_measure

                    if reaches_awake:
                        pending.append(child)
                    else:
                        fixes.append(DeleteRequest(target=child))

        return fixes
