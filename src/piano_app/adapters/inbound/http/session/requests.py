from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Surrounding whitespace is dropped before the length check, so a blank name is refused and
# "clara " is the same account as "clara" (the frontend trims too).
type Username = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)
    username: Username | None = None


class PasswordRegisterRequest(BaseModel):
    username: Username
    password: str = Field(min_length=8, max_length=128)


class PasswordLoginRequest(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=128)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class GoogleLinkRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)
