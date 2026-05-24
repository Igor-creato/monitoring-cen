"""admin runtime settings

Revision ID: 20260524_0004
Revises: 20260524_0003
Create Date: 2026-05-24 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260524_0004"
down_revision: str | None = "20260524_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("user", "admin", native_enum=False),
            nullable=False,
            server_default="user",
        ),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "service_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.alter_column(
        "service_settings",
        "is_secret",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )


def downgrade() -> None:
    op.drop_table("service_settings")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")
