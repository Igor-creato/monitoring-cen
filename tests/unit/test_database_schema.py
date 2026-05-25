from app.infra.db import models
from app.infra.db.base import Base
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import configure_mappers


def test_all_monitoring_tables_are_registered() -> None:
    _ = models
    configure_mappers()

    assert set(Base.metadata.tables) == {
        "audit_logs",
        "monitors",
        "notifications",
        "parser_errors",
        "password_reset_tokens",
        "price_check_daily_stats",
        "price_checks",
        "product_sources",
        "products",
        "service_settings",
        "users",
    }


def test_product_sources_have_url_dedup_constraint() -> None:
    table = Base.metadata.tables["product_sources"]

    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints["uq_product_sources_domain_url_hash"] == (
        "domain",
        "normalized_url_hash",
    )


def test_worker_and_history_indexes_exist() -> None:
    monitors = Base.metadata.tables["monitors"]
    price_checks = Base.metadata.tables["price_checks"]

    monitor_indexes = {
        index.name: tuple(column.name for column in index.columns) for index in monitors.indexes
    }
    price_check_indexes = {
        index.name: tuple(column.name for column in index.columns) for index in price_checks.indexes
    }

    assert monitor_indexes["ix_monitors_status_next_check"] == (
        "status",
        "next_check_at",
        "id",
    )
    assert price_check_indexes["ix_price_checks_source_checked_at"] == (
        "product_source_id",
        "checked_at",
        "id",
    )


def test_notifications_have_dedup_constraint() -> None:
    table = Base.metadata.tables["notifications"]

    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints["uq_notifications_dedupe"] == (
        "monitor_id",
        "type",
        "channel",
        "dedupe_key",
    )


def test_password_reset_token_indexes_exist() -> None:
    table = Base.metadata.tables["password_reset_tokens"]

    indexes = {index.name: tuple(column.name for column in index.columns) for index in table.indexes}

    assert indexes["ix_password_reset_tokens_token_hash"] == ("token_hash",)
    assert indexes["ix_password_reset_tokens_user_id"] == ("user_id",)
    assert indexes["ix_password_reset_tokens_expires_at"] == ("expires_at",)
