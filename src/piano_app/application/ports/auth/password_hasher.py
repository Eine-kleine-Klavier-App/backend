from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PasswordDigest:
    """What is stored for a password: the derived hash and the salt it was derived with."""

    hash: bytes
    salt: bytes


class PasswordHasher(Protocol):
    async def hash(self, *, password: str) -> PasswordDigest:
        """Derives a digest with a fresh random salt."""
        ...

    async def verify(self, *, password: str, digest: PasswordDigest) -> bool: ...
