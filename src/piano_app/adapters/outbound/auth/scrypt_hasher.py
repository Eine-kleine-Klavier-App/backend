import asyncio
import hashlib
import hmac
import secrets
from typing import Final

from piano_app.application.ports.auth import PasswordDigest


class ScryptPasswordHasher:
    _SALT_BYTES: Final[int] = 16
    _KEY_BYTES: Final[int] = 32
    _COST: Final[int] = 2**14
    _BLOCK_SIZE: Final[int] = 8
    _PARALLELISM: Final[int] = 1

    # scrypt is CPU-bound (tens of ms); a worker thread keeps the event loop free.
    async def hash(self, *, password: str) -> PasswordDigest:
        salt: bytes = secrets.token_bytes(self._SALT_BYTES)
        key: bytes = await asyncio.to_thread(self._derive, password=password, salt=salt)

        return PasswordDigest(hash=key, salt=salt)

    async def verify(self, *, password: str, digest: PasswordDigest) -> bool:
        key: bytes = await asyncio.to_thread(self._derive, password=password, salt=digest.salt)

        return hmac.compare_digest(key, digest.hash)

    @classmethod
    def _derive(cls, *, password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=cls._COST,
            r=cls._BLOCK_SIZE,
            p=cls._PARALLELISM,
            dklen=cls._KEY_BYTES,
        )
