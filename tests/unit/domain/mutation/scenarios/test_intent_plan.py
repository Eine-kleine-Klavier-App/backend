import pytest

from piano_app.domain.score.document.services.mutation.compiler import intents

from ...scene import COMPLETED_STAGE, PLANNED_INTENTS, planned_intent

# The seam of the plan-intents tests: a completed stage must export its intents, so a renamed
# or unexported class fails here instead of staying a silent xfail.


@pytest.mark.unit
def test_every_intent_of_a_completed_stage_is_exported_by_the_compiler() -> None:
    missing: list[str] = [
        name
        for name, stage in PLANNED_INTENTS.items()
        if stage <= COMPLETED_STAGE and not hasattr(intents, name)
    ]

    assert missing == []


@pytest.mark.unit
def test_an_intent_outside_the_plan_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        planned_intent("InsertRestIntnet")
