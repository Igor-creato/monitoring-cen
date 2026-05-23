# Notification service

## Data flow

1. `run_monitor_check` fetches a product snapshot and stores `price_checks`.
2. `PriceCheckService` evaluates `current_price <= target_price`.
3. If the condition is false, no notification is created.
4. If the condition is true, the service builds a semantic dedupe key from monitor, channel, URL, target price, current price and currency.
5. If the same semantic notification exists inside `NOTIFICATION_DEDUPE_WINDOW_SECONDS`, a history row is written with status `duplicated` and no delivery job is queued.
6. Otherwise a `pending` notification row is written and `send_notification` is enqueued.
7. `send_notification` marks the row `processing`, renders text, sends through the channel provider and persists the terminal status.

## State machine

```text
price condition false
  -> no row

price condition true
  -> pending
  -> processing
  -> sent

pending/failed
  -> processing
  -> failed
  -> retry pending via ARQ retry

processing
  -> skipped       provider/channel/recipient is not configured

price condition true + duplicate inside window
  -> duplicated    history only, no delivery
```

Terminal MVP statuses are `sent`, `failed`, `skipped`, `duplicated`. `pending` and
`processing` are internal delivery states.

## Providers

Providers implement `NotificationProvider`:

```python
class NotificationProvider(Protocol):
    channel: str

    async def send(self, message: NotificationMessage) -> None: ...
```

`EmailProvider` sends via SMTP. `TelegramProvider` is registered as an optional MVP
stub and returns `skipped` until real Telegram delivery and `telegram_chat_id`
storage are added.

## Retry policy

Delivery failures are retried by ARQ with exponential backoff:

```text
delay = min(
  NOTIFICATION_RETRY_BASE_DELAY_SECONDS * 2 ** (job_try - 1),
  NOTIFICATION_RETRY_MAX_DELAY_SECONDS,
)
```

Provider misconfiguration and missing recipients are not retried; they become
`skipped`. Delivery exceptions become `failed`, are retried up to
`NOTIFICATION_MAX_RETRIES`, and final failures are written to `dead:notifications`.
