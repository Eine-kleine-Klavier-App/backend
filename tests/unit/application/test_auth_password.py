from types import TracebackType
from typing import Self

import pytest

from piano_app.adapters.outbound.auth import ScryptPasswordHasher
from piano_app.application.errors import (
    IdentityAlreadyLinkedError,
    InvalidExternalCredentialError,
    InvalidPasswordCredentialsError,
    UsernameConflictError,
)
from piano_app.application.ports.auth import (
    AccessToken,
    ExternalCredentialVerificationError,
    IdentityLinkConflictError,
    PasswordDigest,
    RotatedRefreshSession,
    UsernameAlreadyExistsError,
    UserProfile,
    VerifiedIdentity,
)
from piano_app.application.use_cases.auth import AuthService, AuthSession


class _Store:
    def __init__(self) -> None:
        self.users: dict[str, str] = {}
        self.identities: dict[tuple[str, str], str] = {}
        self.passwords: dict[str, PasswordDigest] = {}
        self.sessions: dict[str, str] = {}
        self.committed: int = 0


class _Identities:
    def __init__(self, store: _Store) -> None:
        self._store: _Store = store

    async def create_user(self, *, username: str) -> UserProfile:
        if username in self._store.users.values():
            raise UsernameAlreadyExistsError(username=username)
        user_id: str = f"user-{len(self._store.users) + 1}"
        self._store.users[user_id] = username
        return UserProfile(user_id=user_id, username=username)

    async def add_identity(self, *, user_id: str, identity: VerifiedIdentity) -> None:
        key: tuple[str, str] = (identity.authority, identity.subject)
        if key in self._store.identities:
            raise IdentityLinkConflictError
        self._store.identities[key] = user_id

    async def find_user_id(self, *, identity: VerifiedIdentity) -> str | None:
        return self._store.identities.get((identity.authority, identity.subject))

    async def find_user_id_by_username(self, *, username: str) -> str | None:
        for user_id, name in self._store.users.items():
            if name == username:
                return user_id
        return None

    async def find_user(self, *, user_id: str) -> UserProfile | None:
        username: str | None = self._store.users.get(user_id)
        return None if username is None else UserProfile(user_id=user_id, username=username)


class _Credentials:
    def __init__(self, store: _Store) -> None:
        self._store: _Store = store

    async def set_password(self, *, user_id: str, digest: PasswordDigest) -> None:
        self._store.passwords[user_id] = digest

    async def find(self, *, user_id: str) -> PasswordDigest | None:
        return self._store.passwords.get(user_id)


class _Sessions:
    def __init__(self, store: _Store) -> None:
        self._store: _Store = store

    async def create(self, *, user_id: str) -> str:
        credential: str = f"session-{len(self._store.sessions) + 1}"
        self._store.sessions[credential] = user_id
        return credential

    async def rotate(self, *, credential: str) -> RotatedRefreshSession | None:
        raise NotImplementedError

    async def revoke(self, *, credential: str) -> None:
        self._store.sessions.pop(credential, None)

    async def revoke_others(self, *, user_id: str, keep_credential: str | None) -> None:
        self._store.sessions = {
            credential: owner
            for credential, owner in self._store.sessions.items()
            if owner != user_id or credential == keep_credential
        }


class _Uow:
    def __init__(self, store: _Store) -> None:
        self._store: _Store = store
        self.identity_repository: _Identities = _Identities(store)
        self.credential_repository: _Credentials = _Credentials(store)
        self.refresh_session_repository: _Sessions = _Sessions(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self._store.committed += 1

    async def rollback(self) -> None:
        return None


class _Verifier:
    async def verify(self, *, credential: str) -> VerifiedIdentity:
        if credential == "bad":
            raise ExternalCredentialVerificationError
        return VerifiedIdentity(authority="google", subject=credential)


class _Tokens:
    def issue(self, *, user_id: str) -> AccessToken:
        return AccessToken(value=f"token-{user_id}", expires_in_seconds=60)

    def verify(self, *, token: str) -> str:
        return token


def _service(store: _Store) -> AuthService:
    return AuthService(
        identity_verifier=_Verifier(),
        password_hasher=ScryptPasswordHasher(),
        access_tokens=_Tokens(),
        auth_uow_factory=lambda: _Uow(store),
    )


async def test_register_then_login_same_account() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)

    registered: AuthSession = await service.register(username="clara", password="correct horse")
    logged_in: AuthSession = await service.login(username="clara", password="correct horse")

    assert registered.access_token.value == logged_in.access_token.value
    assert len(store.users) == 1


async def test_password_is_stored_only_as_salted_hash() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)

    await service.register(username="clara", password="correct horse")
    await service.register(username="tester", password="correct horse")

    first: PasswordDigest = store.passwords["user-1"]
    second: PasswordDigest = store.passwords["user-2"]
    assert b"correct horse" not in first.hash + first.salt
    assert first.salt != second.salt
    assert first.hash != second.hash


async def test_register_taken_username_conflicts() -> None:
    service: AuthService = _service(_Store())
    await service.register(username="clara", password="correct horse")

    with pytest.raises(UsernameConflictError):
        await service.register(username="clara", password="another pass")


@pytest.mark.parametrize(
    ("username", "password"),
    [("clara", "wrong password"), ("nobody", "correct horse")],
)
async def test_login_rejects_wrong_pair_with_one_error(username: str, password: str) -> None:
    service: AuthService = _service(_Store())
    await service.register(username="clara", password="correct horse")

    with pytest.raises(InvalidPasswordCredentialsError):
        await service.login(username=username, password=password)


class _CountingHasher(ScryptPasswordHasher):
    def __init__(self) -> None:
        self.verifications: int = 0

    async def verify(self, *, password: str, digest: PasswordDigest) -> bool:
        self.verifications += 1
        return await super().verify(password=password, digest=digest)


async def test_every_failed_login_costs_one_password_verification() -> None:
    store: _Store = _Store()
    hasher: _CountingHasher = _CountingHasher()
    service: AuthService = AuthService(
        identity_verifier=_Verifier(),
        password_hasher=hasher,
        access_tokens=_Tokens(),
        auth_uow_factory=lambda: _Uow(store),
    )
    await service.register(username="clara", password="correct horse")
    await service.sign_in(credential="g-google-only", username="googler")

    for username, password in (
        ("clara", "wrong password"),
        ("nobody", "wrong password"),
        ("googler", "wrong password"),
    ):
        before: int = hasher.verifications
        with pytest.raises(InvalidPasswordCredentialsError):
            await service.login(username=username, password=password)
        assert hasher.verifications == before + 1


async def test_google_only_user_cannot_password_login_until_password_set() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)
    google: AuthSession = await service.sign_in(credential="g-clara", username="claranova")
    user_id: str = google.access_token.value.removeprefix("token-")

    with pytest.raises(InvalidPasswordCredentialsError):
        await service.login(username="claranova", password="correct horse")

    await service.set_password(user_id=user_id, password="correct horse", keep_credential=None)
    session: AuthSession = await service.login(username="claranova", password="correct horse")

    assert session.access_token.value == google.access_token.value


async def test_set_password_keeps_only_current_session() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)
    first: AuthSession = await service.register(username="clara", password="correct horse")
    second: AuthSession = await service.login(username="clara", password="correct horse")

    await service.set_password(
        user_id="user-1",
        password="new password",
        keep_credential=first.refresh_credential,
    )

    assert set(store.sessions) == {first.refresh_credential}
    assert second.refresh_credential not in store.sessions
    with pytest.raises(InvalidPasswordCredentialsError):
        await service.login(username="clara", password="correct horse")


async def test_link_google_lets_both_ways_reach_one_account() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)
    registered: AuthSession = await service.register(username="tester", password="correct horse")

    await service.link_google(user_id="user-1", credential="g-tester")
    google: AuthSession = await service.sign_in(credential="g-tester", username=None)

    assert google.access_token.value == registered.access_token.value
    assert len(store.users) == 1


async def test_link_google_refuses_identity_of_another_account() -> None:
    store: _Store = _Store()
    service: AuthService = _service(store)
    await service.sign_in(credential="g-clara", username="claranova")
    await service.register(username="tester", password="correct horse")

    with pytest.raises(IdentityAlreadyLinkedError):
        await service.link_google(user_id="user-2", credential="g-clara")


async def test_link_google_rejects_invalid_credential() -> None:
    service: AuthService = _service(_Store())

    with pytest.raises(InvalidExternalCredentialError):
        await service.link_google(user_id="user-1", credential="bad")
