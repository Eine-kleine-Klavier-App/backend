from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import Refrain, Volta
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    AddRefrainEndingIntent,
    AppendVoltaFragmentIntent,
    CreateVoltaIntent,
    MoveVoltaBoundaryIntent,
    MoveVoltaStartIntent,
    SetVoltaFragmentPassesIntent,
    SetVoltaTimesIntent,
    SplitVoltaFragmentIntent,
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    AppendVoltaFragmentRequest,
    CreateVoltaRequest,
    MoveVoltaBoundaryRequest,
    MoveVoltaStartRequest,
    SetVoltaFragmentPassesRequest,
    SetVoltaTimesRequest,
    SplitVoltaFragmentRequest,
    VoltaFragmentRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


class CreateVoltaCompiler:
    """Compiles the endings of a repeat into one create request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateVoltaIntent,
    ) -> Sequence[MutationRequest]:
        for fragment in intent.fragments:
            if (fragment.end_measure_id is None) != (fragment.end_position is None):
                raise MutationRejectedError(
                    "A fragment's end is a measure and a position, or neither."
                )

        entity_ids: set[str] = {intent.start_measure_id, intent.body_end_measure_id}
        entity_ids.update(
            fragment.end_measure_id
            for fragment in intent.fragments
            if fragment.end_measure_id is not None
        )
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document, entity_ids=tuple(entity_ids)
        )

        def measure(*, measure_id: str) -> Measure:
            return expect_entity(
                entities_by_id=entities_by_id, entity_id=measure_id, expected=Measure
            )

        def fragment_request(*, fragment: VoltaFragmentIntent) -> VoltaFragmentRequest:
            return VoltaFragmentRequest(
                end_measure=(
                    None
                    if fragment.end_measure_id is None
                    else measure(measure_id=fragment.end_measure_id)
                ),
                end_position=fragment.end_position,
                passes=frozenset(fragment.passes),
            )

        return [
            CreateVoltaRequest(
                start_measure=measure(measure_id=intent.start_measure_id),
                start_position=intent.start_position,
                body_end_measure=measure(measure_id=intent.body_end_measure_id),
                body_end_position=intent.body_end_position,
                fragments=tuple(
                    fragment_request(fragment=fragment) for fragment in intent.fragments
                ),
            )
        ]


def _volta_and_measure(
    *,
    document: ScoreDocument,
    volta_id: str,
    measure_id: str | None,
) -> tuple[Volta, Measure | None]:
    entity_ids: tuple[str, ...] = (volta_id,) if measure_id is None else (volta_id, measure_id)
    entities_by_id: dict[str, ScoreEntity] = resolve_entities(
        document=document, entity_ids=entity_ids
    )

    return (
        expect_entity(entities_by_id=entities_by_id, entity_id=volta_id, expected=Volta),
        (
            None
            if measure_id is None
            else expect_entity(
                entities_by_id=entities_by_id, entity_id=measure_id, expected=Measure
            )
        ),
    )


def _refuse_half_place(*, measure_id: str | None, has_position: bool) -> None:
    if (measure_id is None) == has_position:
        raise MutationRejectedError("A place is a measure and a position, or neither.")


def _required(*, measure: Measure | None) -> Measure:
    if measure is None:
        raise MutationRejectedError("A measure is needed here.")

    return measure


class MoveVoltaBoundaryCompiler:
    """Compiles dragging a boundary of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveVoltaBoundaryIntent,
    ) -> Sequence[MutationRequest]:
        _refuse_half_place(measure_id=intent.measure_id, has_position=intent.position is not None)
        volta, measure = _volta_and_measure(
            document=document, volta_id=intent.volta_id, measure_id=intent.measure_id
        )

        return [
            MoveVoltaBoundaryRequest(
                target=volta,
                boundary=intent.boundary,
                measure=measure,
                position=intent.position,
            )
        ]


class MoveVoltaStartCompiler:
    """Compiles a new start of the body of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: MoveVoltaStartIntent,
    ) -> Sequence[MutationRequest]:
        volta, measure = _volta_and_measure(
            document=document, volta_id=intent.volta_id, measure_id=intent.measure_id
        )

        return [
            MoveVoltaStartRequest(
                target=volta, measure=_required(measure=measure), position=intent.position
            )
        ]


class SetVoltaFragmentPassesCompiler:
    """Compiles new passes of a fragment of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetVoltaFragmentPassesIntent,
    ) -> Sequence[MutationRequest]:
        volta, _ = _volta_and_measure(document=document, volta_id=intent.volta_id, measure_id=None)

        return [
            SetVoltaFragmentPassesRequest(
                target=volta,
                fragment=intent.fragment,
                passes=frozenset(intent.passes),
            )
        ]


class SetVoltaTimesCompiler:
    """Compiles a new number of passes of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetVoltaTimesIntent,
    ) -> Sequence[MutationRequest]:
        volta, _ = _volta_and_measure(document=document, volta_id=intent.volta_id, measure_id=None)

        return [SetVoltaTimesRequest(target=volta, times=intent.times)]


class AppendVoltaFragmentCompiler:
    """Compiles adding a fragment after the last one of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AppendVoltaFragmentIntent,
    ) -> Sequence[MutationRequest]:
        _refuse_half_place(measure_id=intent.measure_id, has_position=intent.position is not None)
        volta, measure = _volta_and_measure(
            document=document, volta_id=intent.volta_id, measure_id=intent.measure_id
        )

        return [AppendVoltaFragmentRequest(target=volta, measure=measure, position=intent.position)]


class SplitVoltaFragmentCompiler:
    """Compiles cutting the last fragment of a volta into one update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SplitVoltaFragmentIntent,
    ) -> Sequence[MutationRequest]:
        volta, measure = _volta_and_measure(
            document=document, volta_id=intent.volta_id, measure_id=intent.measure_id
        )

        return [
            SplitVoltaFragmentRequest(
                target=volta, measure=_required(measure=measure), position=intent.position
            )
        ]


class AddRefrainEndingCompiler:
    """Compiles making the first ending of a repeat into deleting the repeat and creating a volta
    over the same stretch: its body is the stretch, its one ending is played in every pass but the
    last. A repeat that lasts to the end of the score has no bar for an ending after it."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AddRefrainEndingIntent,
    ) -> Sequence[MutationRequest]:
        _refuse_half_place(measure_id=intent.measure_id, has_position=intent.position is not None)
        entity_ids: tuple[str, ...] = (
            (intent.refrain_id,)
            if intent.measure_id is None
            else (intent.refrain_id, intent.measure_id)
        )
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document, entity_ids=entity_ids
        )
        refrain: Refrain = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.refrain_id, expected=Refrain
        )
        if refrain.end is None:
            raise MutationRejectedError(
                "A repeat that lasts to the end of the score has no bar for an ending after it."
            )

        ending_end: Measure | None = (
            None
            if intent.measure_id is None
            else expect_entity(
                entities_by_id=entities_by_id, entity_id=intent.measure_id, expected=Measure
            )
        )

        return [
            DeleteRequest(target=refrain),
            CreateVoltaRequest(
                start_measure=refrain.start.measure,
                start_position=refrain.start.position,
                body_end_measure=refrain.end.measure,
                body_end_position=refrain.end.position,
                fragments=(
                    VoltaFragmentRequest(
                        end_measure=ending_end,
                        end_position=intent.position,
                        passes=frozenset(range(1, refrain.times)),
                    ),
                ),
            ),
        ]
