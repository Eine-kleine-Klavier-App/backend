"""username case insensitive

Revision ID: d41f7a9c2b68
Revises: c3a9d1f07e52
Create Date: 2026-11-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d41f7a9c2b68"
down_revision: str | Sequence[str] | None = "c3a9d1f07e52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Usernames are unique ignoring case; the stored spelling is left as it is."""
    collisions: list[tuple[str, list[str]]] = [
        (row[0], row[1])
        for row in op.get_bind().execute(
            sa.text(
                "SELECT lower(username), array_agg(username ORDER BY username) FROM users "
                "GROUP BY lower(username) HAVING count(*) > 1"
            )
        )
    ]
    if collisions:
        raise RuntimeError(
            "Usernames that differ only by case must be resolved before this migration: "
            + "; ".join(", ".join(repr(name) for name in names) for _, names in collisions)
        )

    op.create_index("uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.drop_constraint("users_username_key", "users", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.drop_index("uq_users_username_lower", table_name="users")
