from typing import Protocol

from .password_hasher import PasswordDigest


class CredentialRepository(Protocol):
    async def set_password(self, *, user_id: str, digest: PasswordDigest) -> None:
        """Creates the user's password or replaces the existing one."""
        ...

    async def find(self, *, user_id: str) -> PasswordDigest | None:
        """``None`` for a user who has no password (e.g. Google-only)."""
        ...
