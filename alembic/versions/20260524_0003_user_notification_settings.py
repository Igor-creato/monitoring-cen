"""user notification settings

Revision ID: 20260524_0003
Revises: 20260523_0002
Create Date: 2026-05-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260524_0003"
down_revision: str | None = "20260523_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("default_notification_channel", sa.String(length=64), nullable=True),
    )
    op.alter_column("users", "notifications_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "default_notification_channel")
    op.drop_column("users", "notifications_enabled")
