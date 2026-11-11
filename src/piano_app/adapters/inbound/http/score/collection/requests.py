from pydantic import BaseModel, Field, field_validator


class CollectionNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("The collection needs a name.")
        return name
