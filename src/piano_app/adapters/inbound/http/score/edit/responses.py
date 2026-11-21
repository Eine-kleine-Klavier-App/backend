from pydantic import BaseModel, Field

from piano_app.application.use_cases.score.shared import ScoreState, state_sync

from ..sync import measure_sync_payload


class ScoreEditedResponse(BaseModel):
    sync: dict[str, object] = Field(description="The measures the edit changed")

    @classmethod
    def from_state(cls, state: ScoreState) -> ScoreEditedResponse:
        return cls(sync=measure_sync_payload(sync=state_sync(state=state)))
