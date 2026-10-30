from piano_app.domain.score.document.models.material import Carrier, CarrierOwner
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_beams, is_touching
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateBeamAction,
    UpdateBeamMembersAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateBeamRequest,
    SplitBeamRequest,
    UpdateBeamMembersRequest,
)


def check_beam(*, relation: Beam, geometry: ScoreGeometry) -> MutationAnalysis:
    """Keeps a beam on its runs of short neighbouring members (relation-guard).

    The members break into runs at every member too long for a beam and between every two
    members that are not neighbours. The beam keeps the first run of at least two members;
    every later such run gets a beam of its own; a run of one member has no beam, and with
    no run of two the beam is removed. A beam with a grace member is not judged: a grace
    member has no place of its own on the timeline. Decided before the first yield, on the
    live document.
    """
    leaves: list[LeafRhythmicContainer] = []
    for member in relation.members:
        owner: CarrierOwner = member.owner
        if not isinstance(owner, LeafRhythmicContainer):
            return

        leaves.append(owner)

    runs: list[list[Carrier]] = []
    current: list[Carrier] = []
    for index, member in enumerate(relation.members):
        leaf: LeafRhythmicContainer = leaves[index]
        if _is_too_long(leaf=leaf):
            if current:
                runs.append(current)
            current = []
            continue

        # a run holds consecutive members, so the one before this is its last
        if current and _is_separated(geometry=geometry, first=leaves[index - 1], second=leaf):
            runs.append(current)
            current = []

        current.append(member)

    if current:
        runs.append(current)

    kept: list[list[Carrier]] = [run for run in runs if len(run) >= 2]
    if not kept:
        yield DeleteRequest(target=relation)
        return

    if len(kept[0]) != len(relation.members):
        yield UpdateBeamMembersRequest(target=relation, carriers=tuple(kept[0]))

    for run in kept[1:]:
        yield CreateBeamRequest(carriers=tuple(run))


class SplitBeamAnalyzer:
    """Keeps the first surviving run on the existing beam and creates the other if needed."""

    def analyze(self, *, request: SplitBeamRequest, geometry: ScoreGeometry) -> MutationAnalysis:
        beam = request.target
        members = tuple(beam.members)
        if request.before_carrier not in members:
            raise MutationRejectedError("The split carrier must belong to the beam.")
        boundary = members.index(request.before_carrier)
        if boundary == 0:
            raise MutationRejectedError("A beam cannot be split before its first element.")

        runs = [run for run in (members[:boundary], members[boundary:]) if len(run) >= 2]
        if not runs:
            yield DeleteRequest(target=beam)
            return
        yield UpdateBeamMembersRequest(target=beam, carriers=runs[0])
        if len(runs) == 2:
            yield CreateBeamRequest(carriers=runs[1])


class UpdateBeamMembersAnalyzer:
    """Keeps a beam on a run of its consecutive members; the beam refuses anything else."""

    def analyze(
        self,
        *,
        request: UpdateBeamMembersRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        yield UpdateBeamMembersAction(target=request.target, carriers=request.carriers)


class CreateBeamAnalyzer:
    """Beams carriers together: at least two, none already in another beam, by the rules the
    beam is kept by (relation-guard) — no member of a quarter or longer, each a neighbour of
    the one before it, so the carriers come in time order.

    A beam asked for that breaks those rules is refused rather than repaired; the later runs
    ``check_beam`` beams anew always satisfy them.
    """

    def analyze(
        self,
        *,
        request: CreateBeamRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        if len(request.carriers) < 2:
            raise MutationRejectedError("A beam needs at least two elements.")

        if find_beams(carriers=request.carriers):
            raise MutationRejectedError("An element is already part of another beam.")

        # TODO add support for grace notes
        leaves: list[LeafRhythmicContainer] = []
        for carrier in request.carriers:
            owner: CarrierOwner = carrier.owner
            if not isinstance(owner, LeafRhythmicContainer):
                raise MutationRejectedError("Beams involving grace notes are not yet supported.")

            leaves.append(owner)

        for index, leaf in enumerate(leaves):
            if _is_too_long(leaf=leaf):
                raise MutationRejectedError("An element of a quarter or longer cannot be beamed.")

            if index > 0 and _is_separated(geometry=geometry, first=leaves[index - 1], second=leaf):
                raise MutationRejectedError(
                    "Beamed elements must touch one after another in one voice."
                )

        yield CreateBeamAction(carriers=request.carriers)


def _is_too_long(*, leaf: LeafRhythmicContainer) -> bool:
    """True for a quarter or longer, a rest too. Dots are ignored, so a dotted eighth stays
    and a dotted quarter goes."""
    return leaf.written_size.value.value <= RhythmicValue.QUARTER


def _is_separated(
    *,
    geometry: ScoreGeometry,
    first: LeafRhythmicContainer,
    second: LeafRhythmicContainer,
) -> bool:
    """True when ``second`` is not a neighbour of ``first``, the member before it."""
    return not is_touching(geometry=geometry, first=first, second=second)
