from collections.abc import Sequence

from pydantic import BaseModel, Field

from piano_app.application.ports import CollectionSummary


class CollectionResponse(BaseModel):
    id: str = Field(description="The collection's id")
    name: str = Field(description="The collection's name")
    score_count: int = Field(description="How many scores the collection holds")

    @classmethod
    def from_summary(cls, summary: CollectionSummary) -> CollectionResponse:
        return cls(id=summary.id, name=summary.name, score_count=summary.score_count)


class ScoreCollectionsResponse(BaseModel):
    collection_ids: list[str] = Field(description="The caller's collections that hold the score")

    @classmethod
    def from_ids(cls, collection_ids: Sequence[str]) -> ScoreCollectionsResponse:
        return cls(collection_ids=list(collection_ids))
