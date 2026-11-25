from fractions import Fraction
from typing import Any

from piano_app.application.ports.score import DocumentRecord
from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    JumpRule,
    KeySignatureChange,
    OctaveTransposition,
    Refrain,
    Slur,
    SpanContext,
    StaffScoped,
    SustainHold,
    TempoChange,
    TempoTransition,
    VoiceScoped,
    Volta,
)
from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    MusicalItem,
    Note,
    NoteCarrier,
    Rest,
    RestCarrier,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    Fingering,
    GlissandoType,
    GracePlacement,
    GraceType,
    Ornament,
    RhythmicSize,
    RhythmicValue,
    StemDirection,
)
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.relations import (
    Beam,
    Glissando,
    Relation,
    Tie,
)
from piano_app.domain.score.document.models.structural import (
    Jump,
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)


class _Serializer:
    def __init__(self, *, document: ScoreDocument) -> None:
        self._voices: list[Voice] = list(document.voices)
        self._document: ScoreDocument = document
        self._staffs: list[Staff] = list(document.staffs)
        self._measures: list[Measure] = list(document.measures)
        self._anchors: dict[str, TemporalAnchor] = {}
        self._containers: dict[str, RhythmicContainer] = {}
        self._grace_groups: dict[str, GraceGroup] = {}
        self._graces: dict[str, GraceItem] = {}
        self._carriers: dict[str, Carrier] = {}
        self._items: dict[str, MusicalItem] = {}
        self._relations: dict[str, Relation] = {}
        self._contexts: list[Context] = []

        self._collect(document=document)

    # a plain keyed write is the dedup: registering the same entity twice
    # (reached via two different paths in the graph) is just a harmless overwrite.
    # I expect that no collisions of ids should happen, only revisiting an entity
    def _add[T: ScoreEntity](self, *, into: dict[str, T], entity: T) -> None:
        into[entity.id] = entity

    def _collect(self, *, document: ScoreDocument) -> None:
        for measure in document.measures:
            for anchor in measure.anchors:
                self._add(into=self._anchors, entity=anchor)

                # every context starts at exactly one anchor, so its start anchor reaches it
                # once; restoring replays this order, which rebuilds the anchor's list and
                # the staff and voice indexes (ordered by start, ties newest first)
                for context in anchor.starting_contexts:
                    self._contexts.append(context)

                # every rhythmic container — leaf or group, even an empty group — starts
                # at an anchor, so the anchors reach all of them; restoring resolves
                # parents in waves, so their order here does not matter
                for container in anchor.containers:
                    self._add(into=self._containers, entity=container)
                    if not isinstance(container, LeafRhythmicContainer):
                        continue

                    leaf: LeafRhythmicContainer = container

                    for grace_group in (leaf.grace_before, leaf.grace_after):
                        if grace_group is None:
                            continue

                        self._add(into=self._grace_groups, entity=grace_group)
                        if not grace_group.grace_items:
                            raise ValueError("Grace group must have at least one grace item.")

                        for grace_item in grace_group.grace_items:
                            self._add(into=self._graces, entity=grace_item)
                            self._collect_carrier(carrier=grace_item.carrier)

                    self._collect_carrier(carrier=leaf.carrier)

    def _collect_carrier(self, *, carrier: Carrier | None) -> None:
        """A carrier of a leaf or of a grace item, with what it holds and the relations it is in."""
        if carrier is None:
            raise ValueError("A leaf or a grace item must have a carrier.")

        self._add(into=self._carriers, entity=carrier)
        for carrier_relation in carrier.carrier_group_relations:
            self._add(into=self._relations, entity=carrier_relation)

        if isinstance(carrier, NoteCarrier):
            if not carrier.notes:
                raise ValueError("Note carrier must have at least one note.")

            for note in carrier.notes:
                self._add(into=self._items, entity=note)
                for note_relation in note.relations:
                    self._add(into=self._relations, entity=note_relation)
        elif isinstance(carrier, RestCarrier):
            if carrier.rest is None:
                raise ValueError("Rest carrier must have a rest.")

            self._add(into=self._items, entity=carrier.rest)
        else:
            raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

    def _presentation_json(self) -> dict[str, object]:
        presentation = self._document.presentation
        return {
            "vertical": [
                {
                    "entity_id": target.entity_id,
                    "reference": target.reference.value,
                    "offset": value.value,
                }
                for target, value in presentation.vertical.items()
            ],
            "endpoints": [
                {
                    "entity_id": target.entity_id,
                    "reference": target.reference.value,
                    "left": value.left,
                    "right": value.right,
                }
                for target, value in presentation.endpoints.items()
            ],
            "directions": [
                {
                    "entity_id": target.entity_id,
                    "reference": target.reference.value,
                    "direction": value.value,
                }
                for target, value in presentation.directions.items()
            ],
            "horizontal": [
                {
                    "entity_id": target.entity_id,
                    "reference": target.reference.value,
                    "offset": value.value,
                }
                for target, value in presentation.horizontal.items()
            ],
            "horizontal_endpoints": [
                {
                    "entity_id": target.entity_id,
                    "reference": target.reference.value,
                    "left": value.left,
                    "right": value.right,
                }
                for target, value in presentation.horizontal_endpoints.items()
            ],
        }

    def serialize(self) -> DocumentRecord:
        # Rows are keyed by id. What has an order the model keeps (the notes of a chord, the
        # contexts that start at an anchor, the items of a grace group, the measures …) is
        # written as the owner's list of ids, so the order never depends on how a store keeps
        # an object's keys.
        return {
            "music_revision": self._document.music_revision,
            "presentation": self._presentation_json(),
            "voice_ids": [voice.id for voice in self._voices],
            "staff_ids": [staff.id for staff in self._staffs],
            "measure_ids": [measure.id for measure in self._measures],
            "relation_ids": list(self._relations),
            "tables": {
                "measures": {
                    measure.id: self._serialize_measure(measure=measure)
                    for measure in self._measures
                },
                "anchors": {
                    anchor.id: self._serialize_temporal_anchor(anchor=anchor)
                    for anchor in self._anchors.values()
                },
                "rhythmic": {
                    container.id: self._serialize_rhythmic_container(container=container)
                    for container in self._containers.values()
                },
                "grace_groups": {
                    group.id: self._serialize_grace_group(group=group)
                    for group in self._grace_groups.values()
                },
                "grace_items": {
                    item.id: self._serialize_grace_item(item=item) for item in self._graces.values()
                },
                "carriers": {
                    carrier.id: self._serialize_carrier(carrier=carrier)
                    for carrier in self._carriers.values()
                },
                "musical_items": {
                    item.id: self._serialize_musical_item(item=item)
                    for item in self._items.values()
                },
                "relations": {
                    relation.id: self._serialize_relation(relation=relation)
                    for relation in self._relations.values()
                },
                "contexts": {
                    context.id: self._serialize_context(context=context)
                    for context in self._contexts
                },
            },
        }

    def _serialize_measure(self, *, measure: Measure) -> dict[str, Any]:
        return self._serialize_rhythmic_size(size=measure.time_signature, prefix="time_signature")

    def _serialize_temporal_anchor(self, *, anchor: TemporalAnchor) -> dict[str, Any]:
        return {
            "measure_id": anchor.measure.id,
            **self._serialize_fraction(value=anchor.position.value, prefix="position"),
            "context_ids": [context.id for context in anchor.starting_contexts],
        }

    def _serialize_rhythmic_container(self, *, container: RhythmicContainer) -> dict[str, Any]:
        parent: RhythmicContainerParent = container.parent
        parent_id: str
        if isinstance(parent, (Voice, GroupRhythmicContainer)):
            parent_id = parent.id
        else:
            raise TypeError(f"Unsupported rhythmic container parent type: {type(parent).__name__}.")

        common: dict[str, Any] = {
            "parent_id": parent_id,
            "anchor_id": container.start_anchor.id,
            **self._serialize_rhythmic_size(size=container.written_size, prefix="written"),
            **self._serialize_rhythmic_size(size=container.occupied_size, prefix="occupied"),
        }

        if isinstance(container, LeafRhythmicContainer):
            return common | {
                "kind": "leaf",
            }

        if isinstance(container, GroupRhythmicContainer):
            return common | {
                "kind": "group",
            }

        raise TypeError(f"Unsupported rhythmic container type: {type(container).__name__}.")

    def _serialize_grace_group(self, *, group: GraceGroup) -> dict[str, Any]:
        return {
            "leaf_id": group.leaf.id,
            "grace_type": group.grace_type.value,
            "placement": group.placement.value,
            "grace_item_ids": [item.id for item in group.grace_items],
        }

    def _serialize_grace_item(self, *, item: GraceItem) -> dict[str, Any]:
        return self._serialize_dotted_value(value=item.rhythmic_value, prefix="item")

    def _serialize_carrier(self, *, carrier: Carrier) -> dict[str, Any]:
        owner: CarrierOwner | None = carrier.owner
        if owner is None:
            raise ValueError("Carrier must have an owner.")

        owner_id: str
        if isinstance(owner, (LeafRhythmicContainer, GraceItem)):
            owner_id = owner.id
        else:
            raise TypeError(f"Unsupported carrier owner type: {type(owner).__name__}.")

        common: dict[str, Any] = {
            "owner_id": owner_id,
        }

        if isinstance(carrier, NoteCarrier):
            return common | {
                "kind": "note_carrier",
                "articulations": [
                    articulation.value for articulation in sorted(carrier.articulations)
                ],
                "ornament": carrier.ornament.value,
                "note_ids": [note.id for note in carrier.notes],
            }

        if isinstance(carrier, RestCarrier):
            if carrier.rest is None:
                raise ValueError("Rest carrier must have a rest.")

            return common | {
                "kind": "rest_carrier",
                "rest_id": carrier.rest.id,
            }

        raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

    def _serialize_musical_item(self, *, item: MusicalItem) -> dict[str, Any]:
        common: dict[str, Any] = {
            "staff_id": item.staff.id,
        }

        if isinstance(item, Note):
            return common | {
                "kind": "note",
                "staff_step": item.staff_step,
                "accidental": item.accidental.value,
                "fingering": item.fingering.value,
            }

        if isinstance(item, Rest):
            return common | {
                "kind": "rest",
            }

        raise TypeError(f"Unsupported musical item type: {type(item).__name__}.")

    def _serialize_relation(self, *, relation: Relation) -> dict[str, Any]:
        if isinstance(relation, Tie):
            return {
                "kind": "tie",
                "start_note_id": relation.start.id,
                "end_note_id": relation.end.id,
            }

        if isinstance(relation, Glissando):
            return {
                "kind": "glissando",
                "start_note_id": relation.start.id,
                "end_note_id": relation.end.id,
                "glissando_type": relation.glissando_type.value,
            }

        if isinstance(relation, Beam):
            return {
                "kind": "beam",
                "carrier_ids": [carrier.id for carrier in relation.members],
            }

        raise TypeError(f"Unsupported relation type: {type(relation).__name__}.")

    def _serialize_jump_rule(self, *, rule: JumpRule) -> dict[str, Any]:
        """A jump of a volta; an end that is the end of the score has no anchor."""
        return {
            "jump_id": rule.jump.id,
            "source_anchor_id": None if rule.jump.source is None else rule.jump.source.id,
            "target_anchor_id": None if rule.jump.target is None else rule.jump.target.id,
            "arrivals": sorted(rule.arrivals),
        }

    def _serialize_context(self, *, context: Context) -> dict[str, Any]:
        # the form and scope axes add their links; the kind alone names both, so a
        # score-scoped context simply has no scope key
        common: dict[str, Any] = {}
        if isinstance(context, SpanContext):
            common |= {"end_anchor_id": None if context.end is None else context.end.id}
        if isinstance(context, StaffScoped):
            common |= {"staff_id": context.staff.id}
        if isinstance(context, VoiceScoped):
            common |= {"voice_id": context.voice.id}

        if isinstance(context, TempoChange):
            return common | {
                "kind": "tempo_change",
                **self._serialize_dotted_value(value=context.beat, prefix="beat"),
                "bpm": context.bpm,
                "show_label": context.show_label,
            }

        if isinstance(context, ClefChange):
            return common | {
                "kind": "clef_change",
                "clef": context.clef.value,
                "octave_transposition": context.octave_transposition,
            }

        if isinstance(context, KeySignatureChange):
            return common | {
                "kind": "key_signature_change",
                "alterations": [alteration.value for alteration in context.alterations],
            }

        if isinstance(context, DynamicChange):
            return common | {
                "kind": "dynamic_change",
                "dynamic": context.dynamic.value,
            }

        if isinstance(context, SustainHold):
            return common | {
                "kind": "sustain_hold",
            }

        if isinstance(context, Refrain):
            return common | {
                "kind": "refrain",
                "end_anchor_id": None if context.end is None else context.end.id,
                "jump_id": context.jump.id,
                "times": context.times,
            }

        if isinstance(context, Volta):
            return common | {
                "kind": "volta",
                "backs": [self._serialize_jump_rule(rule=rule) for rule in context.backs],
                "skips": [self._serialize_jump_rule(rule=rule) for rule in context.skips],
            }

        if isinstance(context, OctaveTransposition):
            return common | {
                "kind": "octave_transposition",
                "octaves": context.octaves,
            }

        if isinstance(context, Hairpin):
            return common | {
                "kind": "hairpin",
                "steps": context.steps,
            }

        if isinstance(context, TempoTransition):
            return common | {
                "kind": "tempo_transition",
                **self._serialize_fraction(value=context.ratio, prefix="ratio"),
            }

        if isinstance(context, Slur):
            return common | {
                "kind": "slur",
            }

        raise TypeError(f"Unsupported context type: {type(context).__name__}.")

    def _serialize_dotted_value(self, *, value: DottedRhythmicValue, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_value": int(value.value),
            f"{prefix}_dots": value.dots_count,
        }

    def _serialize_rhythmic_size(self, *, size: RhythmicSize, prefix: str) -> dict[str, Any]:
        return {
            **self._serialize_dotted_value(value=size.value, prefix=prefix),
            f"{prefix}_count": size.count,
        }

    def _serialize_fraction(self, *, value: Fraction, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_numerator": value.numerator,
            f"{prefix}_denominator": value.denominator,
        }


class _Deserializer:
    """Rebuilds a ScoreDocument from `_Serializer`'s flat tables.

    Each ``_build_*`` step resolves its rows' foreign keys against the
    already-built id maps from earlier steps, then reconstructs via each
    entity's `.reconstruct()`.
    """

    def _row(self, *, table: str, row_id: str) -> dict[str, Any]:
        """A row of a table, with the id it is keyed by."""
        return {"id": row_id, **self._tables[table][row_id]}

    def _rows(self, *, table: str) -> list[dict[str, Any]]:
        return [{"id": row_id, **row} for row_id, row in self._tables[table].items()]

    def _end_anchor(self, *, row: dict[str, Any]) -> TemporalAnchor | None:
        """The anchor a stored span ends at, or None for one lasting until the score ends."""
        anchor_id: str | None = row["end_anchor_id"]
        return None if anchor_id is None else self._anchors_by_id[anchor_id]

    def __init__(self, *, data: dict[str, Any]) -> None:
        self._data: dict[str, Any] = data

        self._tables: dict[str, dict[str, dict[str, Any]]] = data["tables"]

        self._voices_by_id: dict[str, Voice] = {
            voice_id: Voice(id=voice_id) for voice_id in data["voice_ids"]
        }
        self._staffs_by_id: dict[str, Staff] = {
            staff_id: Staff(id=staff_id) for staff_id in data["staff_ids"]
        }

        self._document: ScoreDocument = ScoreDocument.create(
            voices=list(self._voices_by_id.values()),
            staffs=list(self._staffs_by_id.values()),
            measures=[],
        )

        self._measures_by_id: dict[str, Measure] = self._build_measures()
        self._anchors_by_id: dict[str, TemporalAnchor] = self._build_anchors()
        self._containers_by_id: dict[str, RhythmicContainer] = self._build_rhythmic_containers()
        self._grace_groups_by_id: dict[str, GraceGroup] = self._build_grace_groups()
        self._grace_items_by_id: dict[str, GraceItem] = self._build_grace_items()

        self._carrier_owners_by_id: dict[str, CarrierOwner] = {
            **{
                container.id: container
                for container in self._containers_by_id.values()
                if isinstance(container, LeafRhythmicContainer)
            },
            **self._grace_items_by_id,
        }
        self._carriers_by_id: dict[str, Carrier] = self._build_carriers()
        self._notes_by_id: dict[str, Note] = self._build_musical_items()
        self._build_relations()
        self._build_contexts()
        self._build_presentation()

    @staticmethod
    def _target(*, row: dict[str, Any]) -> PresentationTarget:
        return PresentationTarget(
            entity_id=row["entity_id"], reference=ReferencePoint(row["reference"])
        )

    def _build_presentation(self) -> None:
        self._document.set_music_revision(revision=self._data["music_revision"])
        presentation = self._document.presentation
        data: dict[str, Any] = self._data["presentation"]
        for row in data["vertical"]:
            presentation.set_vertical(
                target=self._target(row=row),
                value=VerticalOffset(value=row["offset"]),
            )
        for row in data["endpoints"]:
            presentation.set_endpoints(
                target=self._target(row=row),
                value=EndpointOffsets(left=row["left"], right=row["right"]),
            )
        for row in data["directions"]:
            presentation.set_direction(
                target=self._target(row=row),
                value=StemDirection(row["direction"]),
            )
        for row in data["horizontal"]:
            presentation.set_horizontal(
                target=self._target(row=row),
                value=HorizontalOffset(value=row["offset"]),
            )
        for row in data["horizontal_endpoints"]:
            presentation.set_horizontal_endpoints(
                target=self._target(row=row),
                value=HorizontalEndpointOffsets(left=row["left"], right=row["right"]),
            )

    def deserialize(self) -> ScoreDocument:
        missing: list[str] = self._document.missing_initial_contexts()
        if missing:
            raise ValueError(
                f"The saved score lacks what every score holds at its start: {', '.join(missing)}."
            )

        return self._document

    def _build_measures(self) -> dict[str, Measure]:
        by_id: dict[str, Measure] = {}
        for measure_id in self._data["measure_ids"]:
            row: dict[str, Any] = self._row(table="measures", row_id=measure_id)
            measure: Measure = Measure.reconstruct(
                id=row["id"],
                time_signature=self._rhythmic_size(row=row, prefix="time_signature"),
            )
            self._document.append_measure(measure=measure)
            by_id[row["id"]] = measure

        return by_id

    def _build_anchors(self) -> dict[str, TemporalAnchor]:
        by_id: dict[str, TemporalAnchor] = {}
        for row in self._rows(table="anchors"):
            by_id[row["id"]] = TemporalAnchor.reconstruct(
                id=row["id"],
                measure=self._measures_by_id[row["measure_id"]],
                position=MeasurePosition.of_fraction(
                    fraction=self._fraction(row=row, prefix="position"),
                ),
            )

        return by_id

    def _build_rhythmic_containers(self) -> dict[str, RhythmicContainer]:
        by_id: dict[str, RhythmicContainer] = {}
        # only groups can ever be a parent, so keep them separately
        groups_by_id: dict[str, GroupRhythmicContainer] = {}
        remaining: list[dict[str, Any]] = self._rows(table="rhythmic")

        # despite serialising hierarchy in the order that allows for always hitting resolve,
        # I add additional protection by resolving in waves
        while remaining:
            unresolved: list[dict[str, Any]] = []
            for row in remaining:
                parent: RhythmicContainerParent | None = self._voices_by_id.get(
                    row["parent_id"]
                ) or groups_by_id.get(row["parent_id"])

                if parent is None:
                    unresolved.append(row)
                    continue

                container: RhythmicContainer = self._build_rhythmic_container(
                    row=row, parent=parent
                )
                by_id[row["id"]] = container
                if isinstance(container, GroupRhythmicContainer):
                    groups_by_id[row["id"]] = container

            if len(unresolved) == len(remaining):
                raise ValueError(
                    "Cannot resolve rhythmic container parents (cycle or missing parent)."
                )

            remaining = unresolved

        return by_id

    def _build_rhythmic_container(
        self,
        *,
        row: dict[str, Any],
        parent: RhythmicContainerParent,
    ) -> RhythmicContainer:
        written_size: RhythmicSize = self._rhythmic_size(row=row, prefix="written")
        occupied_size: RhythmicSize = self._rhythmic_size(row=row, prefix="occupied")

        kind: str = row["kind"]
        if kind == "leaf":
            return LeafRhythmicContainer.reconstruct(
                id=row["id"],
                parent=parent,
                anchor=self._anchors_by_id[row["anchor_id"]],
                size=written_size,
            )

        if kind == "group":
            return GroupRhythmicContainer.reconstruct(
                id=row["id"],
                parent=parent,
                anchor=self._anchors_by_id[row["anchor_id"]],
                written_size=written_size,
                occupied_size=occupied_size,
            )

        raise ValueError(f"Unsupported rhythmic container kind: {kind}.")

    def _build_grace_groups(self) -> dict[str, GraceGroup]:
        by_id: dict[str, GraceGroup] = {}
        for row in self._rows(table="grace_groups"):
            leaf: RhythmicContainer = self._containers_by_id[row["leaf_id"]]
            if not isinstance(leaf, LeafRhythmicContainer):
                raise TypeError(f"Grace group's leaf_id does not resolve to a leaf: {leaf.id!r}.")

            by_id[row["id"]] = GraceGroup.reconstruct(
                id=row["id"],
                leaf=leaf,
                grace_type=GraceType(row["grace_type"]),
                placement=GracePlacement(row["placement"]),
            )

        return by_id

    def _build_grace_items(self) -> dict[str, GraceItem]:
        by_id: dict[str, GraceItem] = {}
        for group_row in self._rows(table="grace_groups"):
            for item_id in group_row["grace_item_ids"]:
                row: dict[str, Any] = self._row(table="grace_items", row_id=item_id)
                by_id[item_id] = GraceItem.reconstruct(
                    id=item_id,
                    grace_group=self._grace_groups_by_id[group_row["id"]],
                    rhythmic_value=DottedRhythmicValue(
                        value=RhythmicValue(row["item_value"]),
                        dots_count=row["item_dots"],
                    ),
                )

        return by_id

    def _build_carriers(self) -> dict[str, Carrier]:
        by_id: dict[str, Carrier] = {}
        for row in self._rows(table="carriers"):
            owner: CarrierOwner = self._carrier_owners_by_id[row["owner_id"]]

            kind: str = row["kind"]
            if kind == "note_carrier":
                by_id[row["id"]] = NoteCarrier.reconstruct(
                    id=row["id"],
                    owner=owner,
                    articulations=frozenset(Articulation(value) for value in row["articulations"]),
                    ornament=Ornament(row["ornament"]),
                )
            elif kind == "rest_carrier":
                by_id[row["id"]] = RestCarrier.reconstruct(id=row["id"], owner=owner)
            else:
                raise ValueError(f"Unsupported carrier kind: {kind}.")

        return by_id

    def _build_musical_items(self) -> dict[str, Note]:
        notes_by_id: dict[str, Note] = {}
        for carrier_row in self._rows(table="carriers"):
            carrier: Carrier = self._carriers_by_id[carrier_row["id"]]
            if isinstance(carrier, NoteCarrier):
                for note_id in carrier_row["note_ids"]:
                    row: dict[str, Any] = self._row(table="musical_items", row_id=note_id)
                    if row["kind"] != "note":
                        raise TypeError(
                            f"A note carrier holds a musical item that is no note: {note_id!r}."
                        )

                    notes_by_id[note_id] = Note.reconstruct(
                        id=note_id,
                        note_carrier=carrier,
                        staff=self._staffs_by_id[row["staff_id"]],
                        staff_step=row["staff_step"],
                        accidental=Accidental(row["accidental"]),
                        fingering=Fingering(row["fingering"]),
                    )
            elif isinstance(carrier, RestCarrier):
                rest_id: str = carrier_row["rest_id"]
                row = self._row(table="musical_items", row_id=rest_id)
                if row["kind"] != "rest":
                    raise TypeError(
                        f"A rest carrier holds a musical item that is no rest: {rest_id!r}."
                    )

                Rest.reconstruct(
                    id=rest_id,
                    rest_carrier=carrier,
                    staff=self._staffs_by_id[row["staff_id"]],
                )
            else:
                raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

        return notes_by_id

    def _build_relations(self) -> None:
        for relation_id in self._data["relation_ids"]:
            row: dict[str, Any] = self._row(table="relations", row_id=relation_id)
            kind: str = row["kind"]
            if kind == "tie":
                Tie.reconstruct(
                    id=row["id"],
                    start_note=self._notes_by_id[row["start_note_id"]],
                    end_note=self._notes_by_id[row["end_note_id"]],
                )
            elif kind == "glissando":
                Glissando.reconstruct(
                    id=row["id"],
                    start_note=self._notes_by_id[row["start_note_id"]],
                    end_note=self._notes_by_id[row["end_note_id"]],
                    glissando_type=GlissandoType(row["glissando_type"]),
                )
            elif kind == "beam":
                Beam.reconstruct(
                    id=row["id"],
                    carriers=[self._carriers_by_id[cid] for cid in row["carrier_ids"]],
                )
            else:
                raise ValueError(f"Unsupported relation kind: {kind}.")

    def _build_contexts(self) -> None:
        # rebuilt measure by measure, anchor by anchor, in each anchor's own order, so each
        # anchor's starting contexts and every staff and voice index come back as they were;
        # an anchor's ending contexts come back in start order
        for measure in self._document.measures:
            for start in measure.anchors:
                for context_id in self._tables["anchors"][start.id]["context_ids"]:
                    self._build_context(
                        row=self._row(table="contexts", row_id=context_id), start=start
                    )

    def _build_context(self, *, row: dict[str, Any], start: TemporalAnchor) -> None:
        kind: str = row["kind"]
        if kind == "tempo_change":
            TempoChange.reconstruct(
                id=row["id"],
                start=start,
                beat=DottedRhythmicValue(
                    value=RhythmicValue(row["beat_value"]), dots_count=row["beat_dots"]
                ),
                bpm=row["bpm"],
                show_label=row["show_label"],
            )
        elif kind == "clef_change":
            ClefChange.reconstruct(
                id=row["id"],
                start=start,
                staff=self._staffs_by_id[row["staff_id"]],
                clef=Clef(row["clef"]),
                octave_transposition=row["octave_transposition"],
            )
        elif kind == "key_signature_change":
            KeySignatureChange.reconstruct(
                id=row["id"],
                start=start,
                staff=self._staffs_by_id[row["staff_id"]],
                alterations=tuple(Accidental(value) for value in row["alterations"]),
            )
        elif kind == "dynamic_change":
            DynamicChange.reconstruct(
                id=row["id"],
                start=start,
                voice=self._voices_by_id[row["voice_id"]],
                dynamic=DynamicMarking(row["dynamic"]),
            )
        elif kind == "sustain_hold":
            SustainHold.reconstruct(
                id=row["id"],
                start=start,
                end=self._end_anchor(row=row),
            )
        elif kind == "refrain":
            Refrain.reconstruct(
                id=row["id"],
                start=start,
                jump=Jump.reconstruct(
                    id=row["jump_id"], source=self._end_anchor(row=row), target=start
                ),
                times=row["times"],
            )
        elif kind == "volta":
            Volta.reconstruct(
                id=row["id"],
                start=start,
                backs=[self._jump_rule(row=rule) for rule in row["backs"]],
                skips=[self._jump_rule(row=rule) for rule in row["skips"]],
            )
        elif kind == "octave_transposition":
            OctaveTransposition.reconstruct(
                id=row["id"],
                start=start,
                end=self._end_anchor(row=row),
                staff=self._staffs_by_id[row["staff_id"]],
                octaves=row["octaves"],
            )
        elif kind == "hairpin":
            Hairpin.reconstruct(
                id=row["id"],
                start=start,
                end=self._end_anchor(row=row),
                voice=self._voices_by_id[row["voice_id"]],
                steps=row["steps"],
            )
        elif kind == "tempo_transition":
            TempoTransition.reconstruct(
                id=row["id"],
                start=start,
                end=self._end_anchor(row=row),
                ratio=self._fraction(row=row, prefix="ratio"),
            )
        elif kind == "slur":
            Slur.reconstruct(
                id=row["id"],
                start=start,
                end=self._end_anchor(row=row),
                voice=self._voices_by_id[row["voice_id"]],
            )
        else:
            raise ValueError(f"Unsupported context kind: {kind}.")

    def _jump_rule(self, *, row: dict[str, Any]) -> JumpRule:
        source_id: str | None = row["source_anchor_id"]
        target_id: str | None = row["target_anchor_id"]
        return JumpRule(
            jump=Jump.reconstruct(
                id=row["jump_id"],
                source=None if source_id is None else self._anchors_by_id[source_id],
                target=None if target_id is None else self._anchors_by_id[target_id],
            ),
            arrivals=frozenset(row["arrivals"]),
        )

    @staticmethod
    def _rhythmic_size(*, row: dict[str, Any], prefix: str) -> RhythmicSize:
        return RhythmicSize(
            value=DottedRhythmicValue(
                value=RhythmicValue(row[f"{prefix}_value"]),
                dots_count=row[f"{prefix}_dots"],
            ),
            count=row[f"{prefix}_count"],
        )

    @staticmethod
    def _fraction(*, row: dict[str, Any], prefix: str) -> Fraction:
        return Fraction(
            numerator=row[f"{prefix}_numerator"],
            denominator=row[f"{prefix}_denominator"],
        )


class CodecError(Exception):
    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ScoreDocumentCodec:
    def serialize(self, document: ScoreDocument) -> DocumentRecord:
        try:
            serializer: _Serializer = _Serializer(document=document)
            return serializer.serialize()
        except Exception as e:
            raise CodecError(reason=str(e)) from e

    def deserialize(self, data: DocumentRecord) -> ScoreDocument:
        try:
            deserializer: _Deserializer = _Deserializer(data=data)
            return deserializer.deserialize()
        except Exception as e:
            raise CodecError(reason=str(e)) from e
