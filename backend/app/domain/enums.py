from enum import StrEnum


class Marketplace(StrEnum):
    OZON = "ozon"
    WILDBERRIES = "wildberries"
    YANDEX_MARKET = "yandex_market"
    UNKNOWN = "unknown"


class MonitorStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    TRIGGERED = "triggered"
    FAILED = "failed"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"
    DELETED = "deleted"


class CheckStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    NOT_MODIFIED = "not_modified"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEDUPED = "deduped"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    DELETED = "deleted"


class AvailabilityStatus(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class NotificationType(StrEnum):
    PRICE_DROP = "price_drop"
    TARGET_REACHED = "target_reached"
    BACK_IN_STOCK = "back_in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PRICE_CHANGED = "price_changed"
    MONITOR_ERROR = "monitor_error"
