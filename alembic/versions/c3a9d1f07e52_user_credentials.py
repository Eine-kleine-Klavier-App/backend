"""user credentials

Revision ID: c3a9d1f07e52
Revises: 87c1b5e0c6a2
Create Date: 2026-11-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a9d1f07e52"
down_revision: str | Sequence[str] | None = "87c1b5e0c6a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A password (salted hash) a user may have next to a linked external identity."""
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("password_hash", sa.LargeBinary(), nullable=False),
        sa.Column("password_salt", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_credentials")
