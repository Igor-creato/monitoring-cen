# Price Monitoring MVP API

Base paths are exposed at `/` and, for compatibility, at `/api/v1` without OpenAPI duplication.

## Endpoints

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/register` | No | `RegisterRequest` | `201 TokenResponse` |
| `POST` | `/auth/login` | No | `LoginRequest` | `200 TokenResponse` |
| `POST` | `/monitors` | Bearer JWT | `MonitorCreateRequest` | `201 MonitorResponse` |
| `GET` | `/monitors?limit=&offset=&status=` | Bearer JWT | Query params | `200 MonitorsListResponse` |
| `GET` | `/monitors/{id}` | Bearer JWT | Path id | `200 MonitorResponse` |
| `PATCH` | `/monitors/{id}` | Bearer JWT | `MonitorUpdateRequest` | `200 MonitorResponse` |
| `DELETE` | `/monitors/{id}` | Bearer JWT | Path id | `204 No Content` |
| `GET` | `/products/{id}/history?limit=&offset=` | Bearer JWT | Query params | `200 ProductHistoryResponse` |
| `POST` | `/internal/check-monitor/{id}` | `X-Internal-Token` | Path id | `202 PriceCheckResponse` |
| `GET` | `/health` | No | Empty | `200 {"status":"ok"}` |

## DTO

`RegisterRequest`: `email`, `password`.

`LoginRequest`: `email`, `password`.

`TokenResponse`: `access_token`, `token_type`, `expires_at`, `user`.

`MonitorCreateRequest`: `url`, optional `target_price`, `check_interval_seconds`, optional `notification_channel`.

`MonitorUpdateRequest`: optional `target_price`, `check_interval_seconds`, `notification_channel`, `status`.

`MonitorResponse`: monitor id, url, marketplace, target/last price, status, interval, last/next check timestamps, created/updated timestamps.

`MonitorsListResponse`: `total`, `limit`, `offset`, `items`.

`ProductHistoryResponse`: `product_id`, `total`, `limit`, `offset`, `items`.

`PriceHistoryItem`: check id, monitor id, status, price, old price, currency, availability, checked timestamp.

`PriceCheckResponse`: check id, monitor id, status, price, currency, error fields, checked timestamp.

## Error Format

All handled errors use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [],
    "request_id": "optional-client-request-id"
  }
}
```

## Error Codes

| HTTP | Code | Typical reason |
| --- | --- | --- |
| `400` | `domain_error` | Domain invariant violation |
| `401` | `unauthorized` | Missing, invalid, or expired JWT |
| `403` | `forbidden` | Invalid internal token or forbidden operation |
| `404` | `not_found` | Entity does not exist or is not visible to caller |
| `409` | `conflict` | Email already registered |
| `422` | `validation_error` | Invalid input shape, ranges, or enum values |
| `422` | `unsupported_marketplace` | URL marketplace is not supported |
| `429` | `too_many_requests` | Rate limit exceeded, when limiter is enabled |

## Dependency Injection

FastAPI dependencies in `app.api.deps` provide:

- `get_db_session`
- repository factories: monitors, price checks, products, users, notifications
- service factories: auth, monitors, product history, price checks
- `get_current_user` for Bearer JWT auth
- `require_internal_token` for internal endpoints

## Rate Limit Recommendation for `POST /monitors`

Use a Redis-backed limiter keyed by `user_id` with a small burst and daily quota:

- burst: `5` creations per minute
- sustained: `100` active monitor creations per day for MVP
- additionally enforce a database quota on active monitors per user, for example `100`
- return `429 too_many_requests` with `Retry-After`
- exclude updates/deletes from this limiter, but audit them separately
