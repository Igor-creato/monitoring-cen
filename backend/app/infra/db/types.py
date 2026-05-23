from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_values(enum_cls) -> list[str]:
    return [item.value for item in enum_cls]
