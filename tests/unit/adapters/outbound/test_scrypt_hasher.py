from piano_app.adapters.outbound.auth import ScryptPasswordHasher
from piano_app.application.ports.auth import PasswordDigest


async def test_verify_accepts_right_and_rejects_wrong_password() -> None:
    hasher: ScryptPasswordHasher = ScryptPasswordHasher()
    digest: PasswordDigest = await hasher.hash(password="correct horse")

    assert await hasher.verify(password="correct horse", digest=digest)
    assert not await hasher.verify(password="correct hors", digest=digest)


async def test_same_password_gets_different_salt_and_hash() -> None:
    hasher: ScryptPasswordHasher = ScryptPasswordHasher()

    first: PasswordDigest = await hasher.hash(password="correct horse")
    second: PasswordDigest = await hasher.hash(password="correct horse")

    assert first.salt != second.salt
    assert first.hash != second.hash
