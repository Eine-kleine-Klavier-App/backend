from dataclasses import dataclass, field
from fractions import Fraction

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
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
    NoteCarrier,
    RestCarrier,
)
from piano_app.domain.score.document.models.material.primitive import MusicalItem, Note, Rest
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicSize
from piano_app.domain.score.document.models.relations import Beam, Glissando, Relation, Tie
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, ContextValues, Tempo
from piano_app.domain.score.document.services.geometry import conversion
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import taken_from
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.presentation.capabilities import (
    presentation_capabilities,
)

_PRESENTATION_KINDS: tuple[str, ...] = (
    "vertical",
    "endpoints",
    "directions",
    "horizontal",
    "horizontal_endpoints",
)


@dataclass(slots=True)
class _MeasureShare:
    """The entities of the view kept with one measure when the view is cut by measure."""

    containers: list[RhythmicContainer] = field(default_factory=list)
    carriers: list[Carrier] = field(default_factory=list)
    items: list[MusicalItem] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    contexts: list[Context] = field(default_factory=list)
    # the containers of each voice that start in the measure, in the order of the voice
    roots: dict[str, list[str]] = field(default_factory=dict)


class ScoreView:
    def __init__(self, *, document: ScoreDocument) -> None:
        self._document: ScoreDocument = document
        self._staffs: list[Staff] = list(document.staffs)
        self._measures: list[Measure] = list(document.measures)
        self._voices: list[Voice] = list(document.voices)

        # the view is read once, so its geometry and pitch index are built for it alone
        self._geometry: ScoreGeometry = ScoreGeometry(document=document)
        context_index: ContextIndex = ContextIndex(document=document, geometry=self._geometry)
        self._values: ContextValues = ContextValues(contexts=context_index, geometry=self._geometry)
        self._pitch: ScorePitch = ScorePitch(
            document=document, geometry=self._geometry, contexts=context_index
        )
        self._contexts: list[Context] = list(context_index.contexts())

        self._rhythmic_containers: list[RhythmicContainer] = []
        self._carriers: list[Carrier] = []
        self._items: list[MusicalItem] = []
        self._relations: dict[str, Relation] = {}

        # the measure each entity is kept with when the view is cut by measure: a leaf, its
        # carriers and notes and its grace notes with the measure of its anchor, a group with the
        # measure of its first leaf, a tie or glissando with its first note, a beam with its first
        # carrier, a context with the measure it starts in
        self._homes: dict[str, str] = {}
        for voice in self._voices:
            for container in voice.children:
                self._collect(container=container)

        for relation in self._relations.values():
            if isinstance(relation, Beam):
                self._homes[relation.id] = self._homes[relation.members[0].id]
            elif isinstance(relation, Tie | Glissando):
                self._homes[relation.id] = self._homes[relation.start.id]
            else:
                raise TypeError(f"Unsupported relation type: {type(relation).__name__}.")

        for context in self._contexts:
            self._homes[context.id] = context.start.measure.id

        self._shares: dict[str, _MeasureShare] = {
            measure.id: _MeasureShare() for measure in self._measures
        }
        for container in self._rhythmic_containers:
            self._shares[self._homes[container.id]].containers.append(container)
        for carrier in self._carriers:
            self._shares[self._homes[carrier.id]].carriers.append(carrier)
        for item in self._items:
            self._shares[self._homes[item.id]].items.append(item)
        for relation in self._relations.values():
            self._shares[self._homes[relation.id]].relations.append(relation)
        for context in self._contexts:
            self._shares[self._homes[context.id]].contexts.append(context)
        for voice in self._voices:
            for container in voice.children:
                roots: dict[str, list[str]] = self._shares[self._homes[container.id]].roots
                roots.setdefault(voice.id, []).append(container.id)

        # the placement rows by the measure of their entity (None: an entity of no one measure),
        # read the first time the view is cut by measure
        self._presentation_by_home: dict[str | None, dict[str, list[dict[str, object]]]] | None = (
            None
        )
        self._capabilities_by_home: dict[str | None, list[dict[str, object]]] | None = None

    def jsonify(self) -> dict[str, object]:
        return {
            "music_revision": self._document.music_revision,
            "presentation": self._presentation_json(),
            "presentation_capabilities": self._capabilities_json(),
            "insertion_spaces": self._insertion_spaces_json(),
            "staffs": [self._staff_json(staff=staff) for staff in self._staffs],
            "measures": [self._measure_json(measure=measure) for measure in self._measures],
            "voices": [self._voice_json(voice=voice) for voice in self._voices],
            "rhythmic_containers": [
                self._rhythmic_container_json(container=container)
                for container in self._rhythmic_containers
            ],
            "carriers": [self._carrier_json(carrier=carrier) for carrier in self._carriers],
            "items": [self._item_json(item=item) for item in self._items],
            "relations": [
                self._relation_json(relation=relation) for relation in self._relations.values()
            ],
            "contexts": [self._context_json(context=context) for context in self._contexts],
        }

    def header_json(self) -> dict[str, object]:
        """What belongs to no one measure: the revision, the staffs, the measures in their order,
        the voices and the placements of entities kept with no measure. With the shares of all
        measures it is the whole view."""
        return {
            "music_revision": self._document.music_revision,
            "staffs": [self._staff_json(staff=staff) for staff in self._staffs],
            "measure_ids": [measure.id for measure in self._measures],
            "voice_ids": [voice.id for voice in self._voices],
            "presentation": self._presentation_of(home=None),
            "presentation_capabilities": self._capabilities_of(home=None),
        }

    def home_of(self, *, entity_id: str) -> str | None:
        """The id of the measure an entity of the view is kept with; None for an entity of no
        one measure (a staff, a voice) or one the view does not have."""
        return self._homes.get(entity_id)

    def measure_json(self, *, measure: Measure) -> dict[str, object]:
        """The share of one measure in the view: the rows of the entities kept with it, built
        for them alone, in the order of the whole view."""
        share: _MeasureShare = self._shares[measure.id]
        return {
            "measure": self._measure_json(measure=measure),
            "voice_roots": [
                {"voice_id": voice_id, "rhythmic_container_ids": container_ids}
                for voice_id, container_ids in share.roots.items()
            ],
            "rhythmic_containers": [
                self._rhythmic_container_json(container=container) for container in share.containers
            ],
            "carriers": [self._carrier_json(carrier=carrier) for carrier in share.carriers],
            "items": [self._item_json(item=item) for item in share.items],
            "relations": [self._relation_json(relation=relation) for relation in share.relations],
            "contexts": [self._context_json(context=context) for context in share.contexts],
            "insertion_spaces": [
                self._insertion_space_json(group=container)
                for container in share.containers
                if isinstance(container, GroupRhythmicContainer)
            ],
            "presentation": self._presentation_of(home=measure.id),
            "presentation_capabilities": self._capabilities_of(home=measure.id),
        }

    def _presentation_of(self, *, home: str | None) -> dict[str, list[dict[str, object]]]:
        if self._presentation_by_home is None:
            self._presentation_by_home = {}
            for kind, rows in self._presentation_json().items():
                for row in rows:
                    by_kind = self._presentation_by_home.setdefault(
                        self._homes.get(str(row["entity_id"])), {}
                    )
                    by_kind.setdefault(kind, []).append(row)

        found: dict[str, list[dict[str, object]]] = self._presentation_by_home.get(home, {})
        return {kind: found.get(kind, []) for kind in _PRESENTATION_KINDS}

    def _capabilities_of(self, *, home: str | None) -> list[dict[str, object]]:
        if self._capabilities_by_home is None:
            self._capabilities_by_home = {}
            for row in self._capabilities_json():
                self._capabilities_by_home.setdefault(
                    self._homes.get(str(row["entity_id"])), []
                ).append(row)

        return self._capabilities_by_home.get(home, [])

    def _capabilities_json(self) -> list[dict[str, object]]:
        return [
            {
                "entity_id": target.entity_id,
                "reference": target.reference.value,
                "vertical": capability.vertical,
                "endpoints": capability.endpoints,
                "directed": capability.directed,
                "horizontal": capability.horizontal,
                "horizontal_endpoints": capability.horizontal_endpoints,
            }
            for target, capability in presentation_capabilities(document=self._document).items()
        ]

    def _presentation_json(self) -> dict[str, list[dict[str, object]]]:
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

    def _insertion_spaces_json(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for voice in self._voices:
            pending = list(voice.children)
            while pending:
                container = pending.pop(0)
                if not isinstance(container, GroupRhythmicContainer):
                    continue
                result.append(self._insertion_space_json(group=container))
                pending[0:0] = container.children
        return result

    def _insertion_space_json(self, *, group: GroupRhythmicContainer) -> dict[str, object]:
        owner: object = group.parent
        while isinstance(owner, GroupRhythmicContainer):
            owner = owner.parent
        if not isinstance(owner, Voice):
            raise RuntimeError(f"Cannot build score view: group {group.id!r} is in no voice.")

        frame = self._geometry.of_group(group=group)
        transform = conversion(source=frame, target=self._geometry.root)
        return {
            "id": group.id,
            "voice_id": owner.id,
            "parent_id": group.parent.id
            if isinstance(group.parent, GroupRhythmicContainer)
            else None,
            "start": self._fraction_json(value=transform.offset),
            "scale": self._fraction_json(value=transform.scale),
            "extent": self._fraction_json(value=frame.extent),
        }

    def _collect(self, *, container: RhythmicContainer) -> None:
        self._rhythmic_containers.append(container)

        if isinstance(container, GroupRhythmicContainer):
            for child in container.children:
                self._collect(container=child)

            self._homes[container.id] = self._homes[container.children[0].id]

        elif isinstance(container, LeafRhythmicContainer):
            home: str = container.anchor.measure.id
            self._homes[container.id] = home
            carrier: Carrier = self._carrier_of(leaf=container)
            self._carriers.append(carrier)
            self._homes[carrier.id] = home
            for item in self._items_of(carrier=carrier):
                self._items.append(item)
                self._homes[item.id] = home

            for relation in self._relations_of(carrier=carrier):
                self._relations.setdefault(relation.id, relation)

            for group in (container.grace_before, container.grace_after):
                if group is None:
                    continue

                self._homes[group.id] = home
                for grace in group.grace_items:
                    self._homes[grace.id] = home
                    grace_carrier: Carrier = self._grace_carrier_of(grace=grace)
                    self._carriers.append(grace_carrier)
                    self._homes[grace_carrier.id] = home
                    for grace_item in self._items_of(carrier=grace_carrier):
                        self._items.append(grace_item)
                        self._homes[grace_item.id] = home

                    for relation in self._relations_of(carrier=grace_carrier):
                        self._relations.setdefault(relation.id, relation)

        else:
            raise TypeError(f"Unsupported rhythmic container type: {type(container).__name__}.")

    def _staff_json(self, *, staff: Staff) -> dict[str, object]:
        return {"id": staff.id}

    def _measure_json(self, *, measure: Measure) -> dict[str, object]:
        return {
            "id": measure.id,
            "time_signature": self._rhythmic_size_json(size=measure.time_signature),
        }

    def _voice_json(self, *, voice: Voice) -> dict[str, object]:
        return {
            "id": voice.id,
            "rhythmic_container_ids": [container.id for container in voice.children],
        }

    def _rhythmic_container_json(
        self,
        *,
        container: RhythmicContainer,
    ) -> dict[str, object]:
        common: dict[str, object] = {
            "id": container.id,
            "written_size": self._rhythmic_size_json(size=container.written_size),
            "occupied_size": self._rhythmic_size_json(size=container.occupied_size),
        }

        if isinstance(container, GroupRhythmicContainer):
            return common | {
                "kind": "group",
                "child_ids": [child.id for child in container.children],
            }

        if isinstance(container, LeafRhythmicContainer):
            carrier: Carrier = self._carrier_of(leaf=container)
            return common | {
                "kind": "leaf",
                "measure_id": container.anchor.measure.id,
                "position": self._fraction_json(value=container.anchor.position.value),
                "carrier_id": carrier.id,
                "grace_before": self._grace_json(group=container.grace_before),
                "grace_after": self._grace_json(group=container.grace_after),
                # the time its grace notes take from the note: it sounds written minus this
                "grace_taken": self._fraction_json(value=taken_from(leaf=container)),
            }

        raise TypeError(f"Unsupported rhythmic container type: {type(container).__name__}.")

    def _grace_json(self, *, group: GraceGroup | None) -> dict[str, object] | None:
        if group is None:
            return None

        return {
            "id": group.id,
            "grace_type": group.grace_type.value,
            "items": [
                {
                    "id": grace.id,
                    "rhythmic_value": self._dotted_value_json(value=grace.rhythmic_value),
                    "carrier_id": self._grace_carrier_of(grace=grace).id,
                }
                for grace in group.grace_items
            ],
        }

    def _carrier_json(self, *, carrier: Carrier) -> dict[str, object]:
        common: dict[str, object] = {
            "id": carrier.id,
        }

        if isinstance(carrier, NoteCarrier):
            return common | {
                "kind": "chord",
                "articulations": [
                    articulation.value for articulation in sorted(carrier.articulations)
                ],
                "ornament": carrier.ornament.value,
                "note_ids": [note.id for note in carrier.notes],
            }

        if isinstance(carrier, RestCarrier):
            rest: Rest = self._rest_of(carrier=carrier)
            return common | {
                "kind": "rest",
                "rest_id": rest.id,
            }

        raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

    def _item_json(self, *, item: MusicalItem) -> dict[str, object]:
        common: dict[str, object] = {
            "id": item.id,
            "staff_id": item.staff.id,
        }

        if isinstance(item, Note):
            return common | {
                "kind": "note",
                "staff_step": item.staff_step,
                "accidental": item.accidental.value,
                "fingering": int(item.fingering),
                "midi_note": self._midi_note_of(note=item),
            }

        if isinstance(item, Rest):
            return common | {
                "kind": "rest",
            }

        raise TypeError(f"Unsupported musical item type: {type(item).__name__}.")

    def _relation_json(self, *, relation: Relation) -> dict[str, object]:
        common: dict[str, object] = {
            "id": relation.id,
        }

        if isinstance(relation, Tie):
            return common | {
                "kind": "tie",
                "start_note_id": relation.start.id,
                "end_note_id": relation.end.id,
            }

        if isinstance(relation, Beam):
            return common | {
                "kind": "beam",
                "carrier_ids": [carrier.id for carrier in relation.members],
            }

        if isinstance(relation, Glissando):
            return common | {
                "kind": "glissando",
                "start_note_id": relation.start.id,
                "end_note_id": relation.end.id,
                "glissando_type": relation.glissando_type.value,
            }

        raise TypeError(f"Unsupported relation type: {type(relation).__name__}.")

    def _items_of(self, *, carrier: Carrier) -> list[MusicalItem]:
        if isinstance(carrier, NoteCarrier):
            return list(carrier.notes)

        if isinstance(carrier, RestCarrier):
            return [self._rest_of(carrier=carrier)]

        raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

    def _relations_of(self, *, carrier: Carrier) -> list[Relation]:
        relations: list[Relation] = list(carrier.carrier_group_relations)

        if isinstance(carrier, RestCarrier):
            return relations

        if isinstance(carrier, NoteCarrier):
            for note in carrier.notes:
                relations.extend(note.relations)

            return relations

        raise TypeError(f"Unsupported carrier type: {type(carrier).__name__}.")

    def _carrier_of(self, *, leaf: LeafRhythmicContainer) -> Carrier:
        carrier: Carrier | None = leaf.carrier
        if carrier is None:
            raise RuntimeError(f"Cannot build score view: leaf {leaf.id!r} has no carrier.")

        return carrier

    def _grace_carrier_of(self, *, grace: GraceItem) -> Carrier:
        carrier: Carrier | None = grace.carrier
        if carrier is None:
            raise RuntimeError(f"Cannot build score view: grace item {grace.id!r} has no carrier.")

        return carrier

    def _rest_of(self, *, carrier: RestCarrier) -> Rest:
        rest: Rest | None = carrier.rest
        if rest is None:
            raise RuntimeError(f"Cannot build score view: rest carrier {carrier.id!r} has no rest.")

        return rest

    def _rhythmic_size_json(self, *, size: RhythmicSize) -> dict[str, object]:
        value: DottedRhythmicValue = size.value
        return {
            "count": size.count,
            "value": int(value.value),
            "dots": value.dots_count,
        }

    def _fraction_json(self, *, value: Fraction) -> dict[str, object]:
        return {
            "numerator": value.numerator,
            "denominator": value.denominator,
        }

    def _midi_note_of(self, *, note: Note) -> int:
        """The sounding pitch of a note, a grace note included."""
        return self._pitch.pitch_of(note=note).midi_note

    def _context_json(self, *, context: Context) -> dict[str, object]:
        common: dict[str, object] = {
            "id": context.id,
            "measure_id": context.start.measure.id,
            "position": self._fraction_json(value=context.start.position.value),
        }
        if isinstance(context, SpanContext):
            # an empty end lasts until the end of the score
            common |= {
                "end_measure_id": None if context.end is None else context.end.measure.id,
                "end_position": None
                if context.end is None
                else self._fraction_json(value=context.end.position.value),
            }
        if isinstance(context, StaffScoped):
            common |= {"staff_id": context.staff.id}
        if isinstance(context, VoiceScoped):
            common |= {"voice_id": context.voice.id}

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

        if isinstance(context, TempoChange):
            return common | {
                "kind": "tempo_change",
                "beat": self._dotted_value_json(value=context.beat),
                "bpm": context.bpm,
                "show_label": context.show_label,
                "label": None if context.label is None else context.label.value,
            }

        if isinstance(context, DynamicChange):
            return common | {"kind": "dynamic_change", "dynamic": context.dynamic.value}

        if isinstance(context, Hairpin):
            return common | {
                "kind": "hairpin",
                "hairpin_type": context.hairpin_type.value,
                "steps": context.steps,
                "from": self._values.hairpin_start_dynamic(
                    hairpin=context, voice=context.voice
                ).value,
                "to": self._values.hairpin_end_dynamic(hairpin=context, voice=context.voice).value,
            }

        if isinstance(context, TempoTransition):
            return common | {
                "kind": "tempo_transition",
                "ratio": self._fraction_json(value=context.ratio),
                "start_tempo": self._tempo_json(
                    tempo=self._values.transition_start_tempo(transition=context)
                ),
                "end_tempo": self._tempo_json(
                    tempo=self._values.transition_end_tempo(transition=context)
                ),
            }

        if isinstance(context, OctaveTransposition):
            return common | {"kind": "octave_transposition", "octaves": context.octaves}

        if isinstance(context, Slur):
            return common | {"kind": "slur"}

        if isinstance(context, SustainHold):
            return common | {"kind": "sustain_hold"}

        if isinstance(context, Refrain):
            return common | {
                "kind": "refrain",
                "end_measure_id": None if context.end is None else context.end.measure.id,
                "end_position": None
                if context.end is None
                else self._fraction_json(value=context.end.position.value),
                "times": context.times,
            }

        if isinstance(context, Volta):
            return common | {
                "kind": "volta",
                "body_end_measure_id": context.body_end.measure.id,
                "body_end_position": self._fraction_json(value=context.body_end.position.value),
                "pass_count": context.pass_count,
                "fragments": [
                    {
                        "end_measure_id": None if fragment.end is None else fragment.end.measure.id,
                        "end_position": None
                        if fragment.end is None
                        else self._fraction_json(value=fragment.end.position.value),
                        "passes": sorted(fragment.passes),
                    }
                    for fragment in context.fragments
                ],
            }

        raise TypeError(f"Unsupported context type: {type(context).__name__}.")

    def _dotted_value_json(self, *, value: DottedRhythmicValue) -> dict[str, object]:
        return {"value": int(value.value), "dots": value.dots_count}

    def _tempo_json(self, *, tempo: Tempo) -> dict[str, object]:
        return {"beat": self._dotted_value_json(value=tempo.beat), "bpm": float(tempo.bpm)}
