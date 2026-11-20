"""draft record and changes

Revision ID: c3e9a5b17d42
Revises: a27fbc410de5
Create Date: 2026-11-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3e9a5b17d42"
down_revision: str | Sequence[str] | None = "a27fbc410de5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A draft keeps its current record and one change per gesture instead of a whole record per
    revision. The drafts stored so far are in the old format and are removed."""
    op.execute("DELETE FROM draft_meta")
    op.drop_column("draft_contents", "revisions")
    op.add_column(
        "draft_contents",
        sa.Column("record", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.add_column(
        "draft_contents",
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )


def downgrade() -> None:
    """Back to a whole record per revision; the drafts are removed as they cannot be converted."""
    op.execute("DELETE FROM draft_meta")
    op.drop_column("draft_contents", "changes")
    op.drop_column("draft_contents", "record")
    op.add_column(
        "draft_contents",
        sa.Column("revisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
