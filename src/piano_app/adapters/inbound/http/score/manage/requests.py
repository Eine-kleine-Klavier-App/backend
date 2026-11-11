from pydantic import BaseModel, Field, field_validator


class ChangeVisibilityRequest(BaseModel):
    is_public: bool = Field(description="Whether the score should be public")


class ChangeScoreMetadataRequest(BaseModel):
    title: str = Field(min_length=1)
    composer: str | None

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("The score needs a title.")
        return title
