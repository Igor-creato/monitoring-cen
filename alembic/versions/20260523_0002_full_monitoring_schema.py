"""full monitoring schema

Revision ID: 20260523_0002
Revises: 20260523_0001
Create Date: 2026-05-23 00:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260523_0002"
down_revision: str | None = "20260523_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


marketplace_enum = sa.Enum(
    "ozon",
    "wildberries",
    "yandex_market",
    "unknown",
    native_enum=False,
)
availability_enum = sa.Enum(
    "in_stock",
    "out_of_stock",
    "preorder",
    "unknown",
    "unavailable",
    native_enum=False,
)
source_status_enum = sa.Enum(
    "active",
    "inactive",
    "blocked",
    "unsupported",
    "error",
    "deleted",
    native_enum=False,
)
notification_type_enum = sa.Enum(
    "price_drop",
    "target_reached",
    "back_in_stock",
    "out_of_stock",
    "price_changed",
    "monitor_error",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", "deleted", native_enum=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_status", "users", ["status"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=True),
        sa.Column("external_product_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "marketplace",
            "external_product_id",
            name="uq_products_marketplace_external_id",
        ),
    )
    op.create_index("ix_products_marketplace", "products", ["marketplace"], unique=False)

    op.create_table(
        "product_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("normalized_url_hash", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("marketplace", marketplace_enum, nullable=True),
        sa.Column("source_external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("old_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "availability",
            availability_enum,
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("seller_name", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            source_status_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "domain",
            "normalized_url_hash",
            name="uq_product_sources_domain_url_hash",
        ),
        sa.UniqueConstraint(
            "marketplace",
            "source_external_id",
            name="uq_product_sources_marketplace_source_external_id",
        ),
    )
    op.create_index("ix_product_sources_product_id", "product_sources", ["product_id"])
    op.create_index("ix_product_sources_domain", "product_sources", ["domain"])
    op.create_index("ix_product_sources_marketplace", "product_sources", ["marketplace"])
    op.create_index(
        "ix_product_sources_status_last_checked",
        "product_sources",
        ["status", "last_checked_at"],
    )
    op.create_index("ix_product_sources_last_success", "product_sources", ["last_success_at"])

    op.add_column("monitors", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("monitors", sa.Column("product_source_id", sa.Integer(), nullable=True))
    op.add_column("monitors", sa.Column("last_notified_at", sa.DateTime(timezone=True)))
    op.add_column("monitors", sa.Column("error_reason", sa.String(length=255), nullable=True))
    op.add_column("monitors", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("monitors", sa.Column("paused_at", sa.DateTime(timezone=True)))
    op.add_column("monitors", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_monitors_user",
        "monitors",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_monitors_product_source",
        "monitors",
        "product_sources",
        ["product_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_monitors_user_id", "monitors", ["user_id"], unique=False)
    op.create_index(
        "ix_monitors_product_source_id",
        "monitors",
        ["product_source_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitors_status_next_check",
        "monitors",
        ["status", "next_check_at", "id"],
        unique=False,
    )
    op.create_index("ix_monitors_user_status", "monitors", ["user_id", "status"], unique=False)
    op.create_unique_constraint(
        "uq_monitors_user_source_deleted",
        "monitors",
        ["user_id", "product_source_id", "deleted_at"],
    )

    op.add_column("price_checks", sa.Column("product_source_id", sa.Integer(), nullable=True))
    op.add_column("price_checks", sa.Column("old_price", sa.Numeric(18, 4), nullable=True))
    op.add_column(
        "price_checks",
        sa.Column(
            "availability",
            availability_enum,
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("price_checks", sa.Column("seller_name", sa.String(length=512), nullable=True))
    op.add_column("price_checks", sa.Column("title", sa.String(length=1024), nullable=True))
    op.add_column("price_checks", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column("price_checks", sa.Column("response_time_ms", sa.Integer(), nullable=True))
    op.add_column("price_checks", sa.Column("parser_version", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_price_checks_product_source",
        "price_checks",
        "product_sources",
        ["product_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_price_checks_product_source_id",
        "price_checks",
        ["product_source_id"],
        unique=False,
    )
    op.create_index(
        "ix_price_checks_source_checked_at",
        "price_checks",
        ["product_source_id", "checked_at", "id"],
        unique=False,
    )
    op.create_index("ix_price_checks_checked_at", "price_checks", ["checked_at"], unique=False)
    op.create_index(
        "ix_price_checks_status_checked_at",
        "price_checks",
        ["status", "checked_at"],
        unique=False,
    )

    op.add_column("notifications", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("notifications", sa.Column("product_source_id", sa.Integer(), nullable=True))
    op.add_column("notifications", sa.Column("price_check_id", sa.Integer(), nullable=True))
    op.add_column(
        "notifications",
        sa.Column(
            "type",
            notification_type_enum,
            nullable=False,
            server_default="price_changed",
        ),
    )
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=128), nullable=True))
    op.add_column("notifications", sa.Column("scheduled_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column(
        "notifications",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column("notifications", sa.Column("failed_at", sa.DateTime(timezone=True)))

    notifications = sa.table(
        "notifications",
        sa.column("id", sa.Integer()),
        sa.column("dedupe_key", sa.String(length=128)),
    )
    op.get_bind().execute(
        notifications.update()
        .where(notifications.c.dedupe_key.is_(None))
        .values(dedupe_key=sa.literal("legacy:") + sa.cast(notifications.c.id, sa.String(32)))
    )
    op.alter_column(
        "notifications",
        "dedupe_key",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_notifications_user",
        "notifications",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notifications_product_source",
        "notifications",
        "product_sources",
        ["product_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_notifications_price_check",
        "notifications",
        "price_checks",
        ["price_check_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
    op.create_index(
        "ix_notifications_status_scheduled",
        "notifications",
        ["status", "scheduled_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_monitor_created",
        "notifications",
        ["monitor_id", "created_at"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_notifications_dedupe",
        "notifications",
        ["monitor_id", "type", "channel", "dedupe_key"],
    )

    op.create_table(
        "parser_errors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_source_id", sa.Integer(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_source_id"],
            ["product_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_parser_errors_source_occurred",
        "parser_errors",
        ["product_source_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_parser_errors_occurred", "parser_errors", ["occurred_at"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("old_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id", "created_at"],
    )

    op.create_table(
        "price_check_daily_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_source_id", sa.Integer(), nullable=False),
        sa.Column("date_day", sa.Date(), nullable=False),
        sa.Column("min_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("max_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("avg_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("checks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_source_id"],
            ["product_sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_source_id",
            "date_day",
            name="uq_price_check_daily_stats_source_day",
        ),
    )
    op.create_index(
        "ix_price_check_daily_stats_source_day",
        "price_check_daily_stats",
        ["product_source_id", "date_day"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_check_daily_stats_source_day", table_name="price_check_daily_stats")
    op.drop_table("price_check_daily_stats")

    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_parser_errors_occurred", table_name="parser_errors")
    op.drop_index("ix_parser_errors_source_occurred", table_name="parser_errors")
    op.drop_table("parser_errors")

    op.drop_constraint("uq_notifications_dedupe", "notifications", type_="unique")
    op.drop_index("ix_notifications_monitor_created", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_status_scheduled", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_constraint("fk_notifications_price_check", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notifications_product_source", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notifications_user", "notifications", type_="foreignkey")
    op.drop_column("notifications", "failed_at")
    op.drop_column("notifications", "updated_at")
    op.drop_column("notifications", "error_code")
    op.drop_column("notifications", "scheduled_at")
    op.drop_column("notifications", "dedupe_key")
    op.drop_column("notifications", "type")
    op.drop_column("notifications", "price_check_id")
    op.drop_column("notifications", "product_source_id")
    op.drop_column("notifications", "user_id")

    op.drop_index("ix_price_checks_status_checked_at", table_name="price_checks")
    op.drop_index("ix_price_checks_checked_at", table_name="price_checks")
    op.drop_index("ix_price_checks_source_checked_at", table_name="price_checks")
    op.drop_index("ix_price_checks_product_source_id", table_name="price_checks")
    op.drop_constraint("fk_price_checks_product_source", "price_checks", type_="foreignkey")
    op.drop_column("price_checks", "parser_version")
    op.drop_column("price_checks", "response_time_ms")
    op.drop_column("price_checks", "http_status")
    op.drop_column("price_checks", "title")
    op.drop_column("price_checks", "seller_name")
    op.drop_column("price_checks", "availability")
    op.drop_column("price_checks", "old_price")
    op.drop_column("price_checks", "product_source_id")

    op.drop_constraint("uq_monitors_user_source_deleted", "monitors", type_="unique")
    op.drop_index("ix_monitors_user_status", table_name="monitors")
    op.drop_index("ix_monitors_status_next_check", table_name="monitors")
    op.drop_index("ix_monitors_product_source_id", table_name="monitors")
    op.drop_index("ix_monitors_user_id", table_name="monitors")
    op.drop_constraint("fk_monitors_product_source", "monitors", type_="foreignkey")
    op.drop_constraint("fk_monitors_user", "monitors", type_="foreignkey")
    op.drop_column("monitors", "deleted_at")
    op.drop_column("monitors", "paused_at")
    op.drop_column("monitors", "error_code")
    op.drop_column("monitors", "error_reason")
    op.drop_column("monitors", "last_notified_at")
    op.drop_column("monitors", "product_source_id")
    op.drop_column("monitors", "user_id")

    op.drop_index("ix_product_sources_last_success", table_name="product_sources")
    op.drop_index("ix_product_sources_status_last_checked", table_name="product_sources")
    op.drop_index("ix_product_sources_marketplace", table_name="product_sources")
    op.drop_index("ix_product_sources_domain", table_name="product_sources")
    op.drop_index("ix_product_sources_product_id", table_name="product_sources")
    op.drop_table("product_sources")

    op.drop_index("ix_products_marketplace", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
