from sqlalchemy import ScalarResult, Select, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from piano_app.adapters.outbound.postgres.system.schema import UserCredentialModel
from piano_app.application.ports.auth import PasswordDigest


class PostgresCredentialRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
    ) -> None:
        self._session: AsyncSession = session

    async def set_password(self, *, user_id: str, digest: PasswordDigest) -> None:
        statement: Insert = insert(UserCredentialModel).values(
            user_id=user_id,
            password_hash=digest.hash,
            password_salt=digest.salt,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UserCredentialModel.user_id],
            set_={
                "password_hash": statement.excluded.password_hash,
                "password_salt": statement.excluded.password_salt,
            },
        )
        await self._session.execute(statement)

    async def find(self, *, user_id: str) -> PasswordDigest | None:
        query: Select[tuple[UserCredentialModel]] = select(UserCredentialModel).where(
            UserCredentialModel.user_id == user_id,
        )
        result: ScalarResult[UserCredentialModel] = await self._session.scalars(query)
        credential: UserCredentialModel | None = result.one_or_none()

        if credential is None:
            return None

        return PasswordDigest(hash=credential.password_hash, salt=credential.password_salt)
