from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import (
    CarrierOwner,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    split_crossing_groups,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    ClearContextsRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
    RemoveTarget,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    DeleteEmptyMeasureRequest,
)


class RemoveAnalyzer:
    """Removes the listed entities, each through its own delete request.

    Decides no deletion itself: whatever an entity holds is its own analyzer's cascade.
    It only drops what a listed entity already holds and orders the rest — relations, then
    by axis groups, leaves, note carriers, rest carriers, notes, rests, then contexts and
    measures — the listed order kept within each level, so every material level comes
    after the cascades that can remove it. The set is reduced before the first yield;
    before each yield an entity an earlier cascade already removed is skipped, which is a
    no-op, not an error.

    Relations go first, before any material, each once, while they are still the relations
    the intent named. A context is not reduced up front: no cascade takes one, and it comes
    after every material cascade, so the live check is its reduction.

    A measure comes last: whatever was listed inside it is gone or skipped by then. Its
    contexts are cleared out of it first — a context request, which only an intent may
    yield beside rhythm ones — and then the measure goes with everything inside it.
    """

    def analyze(
        self,
        *,
        request: RemoveRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        targets: tuple[RemoveTarget, ...] = request.targets

        listed_groups: list[GroupRhythmicContainer] = [
            target for target in targets if isinstance(target, GroupRhythmicContainer)
        ]
        listed_leaves: list[LeafRhythmicContainer] = [
            target for target in targets if isinstance(target, LeafRhythmicContainer)
        ]
        groups: list[GroupRhythmicContainer] = [
            group for group in listed_groups if not _held(owner=group, groups=listed_groups)
        ]
        leaves: list[LeafRhythmicContainer] = [
            leaf for leaf in listed_leaves if not _held(owner=leaf, groups=listed_groups)
        ]
        note_carriers: list[NoteCarrier] = [
            target
            for target in targets
            if isinstance(target, NoteCarrier)
            and not isinstance(target.owner, GraceItem)
            and target.owner not in listed_leaves
            and not _held(owner=target.owner, groups=listed_groups)
        ]
        rest_carriers: list[RestCarrier] = [
            target
            for target in targets
            if isinstance(target, RestCarrier)
            and not isinstance(target.owner, GraceItem)
            and target.owner not in listed_leaves
            and not _held(owner=target.owner, groups=listed_groups)
        ]
        notes: list[Note] = [
            target
            for target in targets
            if isinstance(target, Note)
            and not isinstance(target.note_carrier.owner, GraceItem)
            and target.note_carrier not in note_carriers
            and target.note_carrier.owner not in listed_leaves
            and not _held(owner=target.note_carrier.owner, groups=listed_groups)
        ]
        rests: list[Rest] = [
            target
            for target in targets
            if isinstance(target, Rest)
            and not isinstance(target.rest_carrier.owner, GraceItem)
            and target.rest_carrier not in rest_carriers
            and target.rest_carrier.owner not in listed_leaves
            and not _held(owner=target.rest_carrier.owner, groups=listed_groups)
        ]

        # A grace note, rest or carrier goes as its item, and an item whose group goes entirely
        # as the group, so no group is left empty. A note of a grace chord goes alone while
        # another note of its carrier stays. What belongs to a note that goes itself is its
        # own cascade.
        grace_items: list[GraceItem] = []
        grace_groups: list[GraceGroup] = []
        for target in targets:
            item: GraceItem | None = None
            if isinstance(target, GraceGroup):
                grace_groups.append(target)
            elif isinstance(target, GraceItem):
                item = target
            elif isinstance(target, NoteCarrier | RestCarrier) and isinstance(
                target.owner, GraceItem
            ):
                item = target.owner
            elif isinstance(target, Rest) and isinstance(target.rest_carrier.owner, GraceItem):
                item = target.rest_carrier.owner
            elif (
                isinstance(target, Note)
                and isinstance(target.note_carrier.owner, GraceItem)
                and all(note in targets for note in target.note_carrier.notes)
            ):
                item = target.note_carrier.owner

            if item is not None and item not in grace_items:
                grace_items.append(item)

        grace_notes: list[Note] = [
            target
            for target in targets
            if isinstance(target, Note)
            and isinstance(target.note_carrier.owner, GraceItem)
            and target.note_carrier.owner not in grace_items
            and target.note_carrier.owner.grace_group not in grace_groups
        ]
        for listed_item in list(grace_items):
            whole: GraceGroup = listed_item.grace_group
            if whole not in grace_groups and all(
                member in grace_items for member in whole.grace_items
            ):
                grace_groups.append(whole)

        # the notes, items and groups of a leaf that goes, with its group, are its own cascade
        grace_groups = [
            group
            for group in grace_groups
            if group.leaf not in listed_leaves and not _held(owner=group.leaf, groups=listed_groups)
        ]
        grace_items = [
            item
            for item in grace_items
            if item.grace_group not in grace_groups
            and item.grace_group.leaf not in listed_leaves
            and not _held(owner=item.grace_group.leaf, groups=listed_groups)
        ]
        grace_notes = [
            note
            for note in grace_notes
            if note.note_carrier.owner not in grace_items
            and isinstance(note.note_carrier.owner, GraceItem)
            and note.note_carrier.owner.grace_group not in grace_groups
            and note.note_carrier.owner.grace_group.leaf not in listed_leaves
            and not _held(owner=note.note_carrier.owner.grace_group.leaf, groups=listed_groups)
        ]

        relations: list[Relation] = []
        for target in targets:
            if isinstance(target, Relation) and not any(target is listed for listed in relations):
                relations.append(target)
        contexts: list[Context] = [target for target in targets if isinstance(target, Context)]
        measures: list[Measure] = [target for target in targets if isinstance(target, Measure)]

        for relation in relations:
            yield DeleteRequest(target=relation)

        # each check reads the live document: an earlier cascade may have removed it
        for group in groups:
            if group in group.parent.children:
                yield DeleteRequest(target=group)

        for leaf in leaves:
            if leaf in leaf.parent.children:
                yield DeleteRequest(target=leaf)

        for grace_group in grace_groups:
            if grace_group in (grace_group.leaf.grace_before, grace_group.leaf.grace_after):
                yield DeleteRequest(target=grace_group)

        for grace_item in grace_items:
            if grace_item in grace_item.grace_group.grace_items:
                yield DeleteRequest(target=grace_item)

        for grace_note in grace_notes:
            if grace_note in grace_note.note_carrier.notes:
                yield DeleteRequest(target=grace_note)

        for note_carrier in note_carriers:
            if note_carrier.owner.carrier is note_carrier:
                yield DeleteRequest(target=note_carrier)

        for rest_carrier in rest_carriers:
            if rest_carrier.owner.carrier is rest_carrier:
                yield DeleteRequest(target=rest_carrier)

        for note in notes:
            if note in note.note_carrier.notes:
                yield DeleteRequest(target=note)

        for rest in rests:
            if rest.rest_carrier.rest is rest:
                yield DeleteRequest(target=rest)

        for context in contexts:
            if context in context.start.starting_contexts:
                yield DeleteRequest(target=context)

        for measure in measures:
            if measure in request.document.measures:
                yield ClearContextsRequest(measure=measure)

                if any(
                    anchor.starting_contexts
                    or anchor.ending_contexts
                    or anchor.departing_jumps
                    or anchor.arriving_jumps
                    for anchor in measure.anchors
                ):
                    raise ValueError(
                        "A removed measure still holds contexts or jumps: they must be cleared "
                        "out of it first."
                    )

                # the groups crossing either barline are split there, so whatever lies inside
                # the measure starts in it
                next_measure: Measure | None = measure.next_measure
                yield from split_crossing_groups(measure=measure, geometry=geometry)
                if next_measure is not None:
                    yield from split_crossing_groups(measure=next_measure, geometry=geometry)

                # read once the splits are done: a second part starting on the first beat is here
                anchors: list[TemporalAnchor] = list(measure.anchors)
                for anchor in anchors:
                    yield DeleteRequest(target=anchor)

                yield DeleteEmptyMeasureRequest(target=measure, document=request.document)


def _held(
    *,
    owner: CarrierOwner | RhythmicContainer,
    groups: list[GroupRhythmicContainer],
) -> bool:
    """Whether one of ``groups`` holds ``owner`` at any depth — that group's cascade
    already deletes it."""
    parent: RhythmicContainerParent | None = (
        owner.parent if isinstance(owner, RhythmicContainer) else None
    )
    while isinstance(parent, GroupRhythmicContainer):
        if parent in groups:
            return True

        parent = parent.parent

    return False
