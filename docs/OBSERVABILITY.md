# Observability для price-monitor

Главная диагностическая цель: быстро понять, почему конкретный внешний сайт перестал отдавать цену: блокировка, таймаут, изменение разметки, ошибка провайдера, неверный URL или внутренняя ошибка сервиса.

## 1. Стратегия логирования

Логи пишутся структурированным JSON через `structlog`. Каждый HTTP-запрос получает `request_id`: сервис берет входящий `X-Request-ID` или генерирует новый, добавляет его в ответ и в контекст логов.

Рекомендуемые поля:

- `event`: стабильное машинное имя события, например `parser.error`.
- `timestamp`, `level`.
- `request_id`: correlation id для API-запроса.
- `error_kind`: `business` или `technical`.
- `error_category`: для технических ошибок: `external_site`, `provider`, `database`, `redis`, `notification`, `internal`.
- `monitor_id`, `product_source_id`, `check_id`, `parser_error_id`.
- `marketplace`, `provider`, `normalized_url_hash` вместо полного URL, если есть риск утечки данных.
- `error_code`, `error_type`, `retryable`.
- `http_status`, `response_time_ms`, `parser_version`.

Business errors:

- ожидаемые состояния домена и пользователя: `validation_error`, `not_found`, `unsupported_marketplace`, `monitor_not_active`, `currency_changed`, `duplicate_notification`;
- обычно `INFO`, иногда `WARNING`, если нужно видеть пользовательскую проблему;
- не отправляются в Sentry как ошибки.

Technical errors:

- сбои инфраструктуры, неожиданные исключения, таймауты, rate limit, блокировки и изменения структуры внешних сайтов;
- `WARNING` для известных retryable/non-fatal ошибок парсинга;
- `ERROR`/`EXCEPTION` для неожиданных ошибок кода, БД, Redis, провайдера или уведомлений;
- отправляются в error tracker с тегами `marketplace`, `provider`, `error_code`.

## 2. Перечень метрик

Обязательные метрики реализованы в `/metrics`:

| Метрика | Тип | Значение |
| --- | --- | --- |
| `monitors_total` | Gauge | Количество не удаленных мониторов |
| `active_monitors` | Gauge | Количество активных мониторов |
| `check_success_rate` | Gauge | Доля успешных проверок за rolling window 15 минут |
| `check_duration` | Histogram | Длительность проверки цены в секундах, label `marketplace` |
| `notification_send_rate` | Gauge | Успешно отправленные уведомления в секунду за 15 минут |
| `parser_error_rate` | Gauge | Ошибки парсинга/внешних сайтов в секунду за 15 минут |

Дополнительные счетчики для PromQL и алертов:

- `price_checks_total{status,marketplace,error_code}`
- `parser_errors_total{marketplace,error_code,retryable}`
- `notification_sends_total{status,channel,error_code}`

Рекомендуемые SLO-индикаторы:

- `check_success_rate >= 0.95` на здоровом трафике;
- `parser_error_rate` отдельно по marketplace, потому что проблемы часто локальны для одного сайта;
- p95 `check_duration` по marketplace;
- рост `provider_timeout`, `provider_blocked`, `page_structure_changed`.

## 3. Пример интеграции Prometheus

Scrape:

```yaml
scrape_configs:
  - job_name: price-monitor-api
    metrics_path: /metrics
    static_configs:
      - targets:
          - api:8000
```

Alerting rules:

```yaml
groups:
  - name: price-monitor
    rules:
      - alert: PriceCheckSuccessRateLow
        expr: check_success_rate < 0.90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Price check success rate dropped
          description: "check_success_rate is {{ $value }} for 10 minutes."

      - alert: ParserErrorRateHigh
        expr: parser_error_rate > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Parser/external-site errors are growing
          description: "parser_error_rate is {{ $value }} errors/sec."

      - alert: MarketplaceParserErrorsHigh
        expr: sum by (marketplace, error_code) (rate(parser_errors_total[10m])) > 0.02
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Parser errors for {{ $labels.marketplace }}"
          description: "{{ $labels.error_code }} is growing for {{ $labels.marketplace }}."

      - alert: PriceCheckP95Slow
        expr: histogram_quantile(0.95, sum by (le, marketplace) (rate(check_duration_bucket[10m]))) > 60
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow price checks for {{ $labels.marketplace }}"
```

## 4. Middleware для request ID

Реализация: `backend/app/infra/request_id.py`.

Поведение:

- читает `X-Request-ID`;
- если заголовка нет, генерирует UUID hex;
- кладет id в `request.state.request_id`;
- биндует `request_id`, `method`, `path` в `structlog.contextvars`;
- возвращает `X-Request-ID` клиенту;
- пишет `api.request_completed` с `status_code` и `duration_ms`.

Для фоновых задач стоит использовать такой же принцип: bind `request_id`/`job_id` в начале ARQ job, чтобы `run_monitor_check`, `parser.error` и `send_notification` связывались одним correlation id.

## 5. Структура `parser_errors`

Текущая таблица подходит для диагностики внешних сайтов:

```text
id
product_source_id
monitor_id
occurred_at
error_code
error_message
parser_version
http_status
response_time_ms
retryable
created_at
```

Рекомендуемые `error_code`:

- `price_not_found`: страница разобрана, но цена не найдена;
- `page_structure_changed`: изменилась структура ответа/разметки;
- `provider_timeout`: провайдер или внешний сайт не ответил вовремя;
- `provider_rate_limited`: rate limit;
- `provider_blocked`: captcha/403/блокировка;
- `provider_payload_error`: невалидный JSON/HTML/ответ провайдера;
- `network_error`: транспортная ошибка;
- `unexpected_product_fetch_error`: неизвестное исключение.

Для отладки полезно держать сырой payload не в `parser_errors`, а в отдельной связанной таблице или object storage с TTL и редактированием секретов. В таблице оставлять короткие индексируемые поля.

## 6. Примеры логов

Business error:

```json
{
  "event": "api.business_error",
  "level": "info",
  "request_id": "5dc7b87c6f7e4b7f9093c27c6d7d94bc",
  "error_kind": "business",
  "error_code": "unsupported_marketplace",
  "status_code": 422,
  "path": "/api/v1/monitors"
}
```

Parser/external-site error:

```json
{
  "event": "parser.error",
  "level": "warning",
  "error_kind": "technical",
  "error_category": "external_site",
  "monitor_id": 42,
  "product_source_id": 17,
  "parser_error_id": 101,
  "marketplace": "wildberries",
  "error_code": "price_not_found",
  "retryable": false
}
```

Unexpected technical error:

```json
{
  "event": "price_check.technical_error",
  "level": "error",
  "error_kind": "technical",
  "monitor_id": 42,
  "error_code": "TimeoutError",
  "exception": "Traceback ..."
}
```

## 7. Sentry и альтернативы

Sentry подходит, если нужен быстрый error tracking с группировкой, stack traces, breadcrumbs, release/version и issue workflow.

Рекомендации для Sentry:

- отправлять только `technical` ошибки;
- `business` ошибки оставлять в логах и метриках;
- поставить tags: `marketplace`, `provider`, `error_code`, `retryable`, `app_env`;
- fingerprint для parser errors: `["parser", marketplace, error_code]`;
- не отправлять полный URL, токены, HTML страниц и payload провайдера без редактирования;
- sampling включить для частых parser errors, иначе при массовом изменении сайта будет шум.

Альтернативы:

- Grafana Loki + Tempo + Prometheus + Alertmanager: хороший self-hosted стек, когда основной сценарий - корреляция логов/метрик/трейсов.
- OpenTelemetry Collector + Jaeger/Tempo: если нужно распределенное трассирование API -> worker -> provider.
- GlitchTip: open-source Sentry-like вариант.
- Rollbar/Bugsnag: managed error tracking, проще Sentry по некоторым workflow.

Минимальный next step: добавить `sentry-sdk[fastapi]`, инициализировать только при `SENTRY_DSN`, а в `before_send` отбрасывать события с `error_kind=business` и чистить URL/payload.
