import pytest
from pydantic import ValidationError

from piano_app.adapters.inbound.http.session.requests import (
    GoogleSignInRequest,
    PasswordLoginRequest,
    PasswordRegisterRequest,
)


def test_username_is_stripped_in_every_request() -> None:
    register: PasswordRegisterRequest = PasswordRegisterRequest(
        username="  qarev_b ", password="correct horse"
    )
    login: PasswordLoginRequest = PasswordLoginRequest(username="qarev_b ", password="x")
    google: GoogleSignInRequest = GoogleSignInRequest(id_token="t", username=" claranova ")

    assert register.username == "qarev_b"
    assert login.username == "qarev_b"
    assert google.username == "claranova"


@pytest.mark.parametrize("username", ["", "   ", "\t\n"])
def test_blank_username_is_refused_everywhere(username: str) -> None:
    with pytest.raises(ValidationError):
        PasswordRegisterRequest(username=username, password="correct horse")
    with pytest.raises(ValidationError):
        PasswordLoginRequest(username=username, password="x")
    with pytest.raises(ValidationError):
        GoogleSignInRequest(id_token="t", username=username)


def test_google_username_stays_optional() -> None:
    assert GoogleSignInRequest(id_token="t").username is None


def test_username_longer_than_64_after_stripping_is_refused() -> None:
    with pytest.raises(ValidationError):
        PasswordRegisterRequest(username="a" * 65, password="correct horse")
