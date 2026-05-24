# MVP Backend Architecture: Price Monitoring By URL

Документ для агента, который будет писать код. Цель: собрать MVP сервиса мониторинга цены по ссылке как один backend-проект без микросервисного фанатизма, но с четкими границами модулей.

## 1. Архитектурная схема словами

Стек:

- Python 3.12
- FastAPI
- SQLAlchemy 2 async
- PostgreSQL или MariaDB
- Redis
- Docker Compose
- Alembic
- httpx
- Pydantic v2
- Arq для фоновых задач

Сервис состоит из одного backend-приложения:

```text
FastAPI API
  -> services / use cases
    -> domain
    -> repositories
      -> SQLAlchemy async
    -> parsers
      -> httpx
    -> notifications
      -> email / telegram / webhook
  -> workers / scheduler
    -> background price checks через Redis + Arq
```

Основной принцип:

- `api` принимает HTTP-запросы, валидирует DTO и вызывает сервисы.
- `services` содержит бизнес-сценарии: создать мониторинг, запустить проверку, обработать результат.
- `domain` содержит бизнес-модель и правила: что такое мониторинг, цена, условие уведомления, статус проверки.
- `repositories` скрывают БД от бизнес-логики.
- `parsers` получают цену по ссылке через адаптер конкретного маркетплейса.
- `workers` выполняют фоновые задачи проверки цен.
- `scheduler` планирует регулярные проверки.
- `notifications` отправляют уведомления.
- `infra` содержит внешнюю инфраструктуру: БД, Redis, настройки, логирование, HTTP-клиенты.

Для MVP выбран Arq.

Почему Arq:

- хорошо ложится на async-стек: FastAPI, SQLAlchemy async, httpx;
- использует Redis, который уже есть в стеке;
- проще Celery для MVP;
- поддерживает retry, cron-задачи и фоновые job;
- не требует лишней инфраструктурной сложности.

Celery можно рассмотреть позже, если появятся сложные workflow, много очередей, routing, отдельные worker pools, Flower и разные SLA для задач.

## 2. Дерево каталогов

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── deps.py
│   │   ├── errors.py
│   │   └── v1/
│   │       ├── router.py
│   │       ├── monitors.py
│   │       ├── checks.py
│   │       └── schemas/
│   │           ├── monitor.py
│   │           ├── check.py
│   │           └── common.py
│   │
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── monitor.py
│   │   │   ├── price_check.py
│   │   │   └── notification.py
│   │   ├── value_objects/
│   │   │   ├── money.py
│   │   │   └── url.py
│   │   ├── enums.py
│   │   └── exceptions.py
│   │
│   ├── repositories/
│   │   ├── interfaces.py
│   │   ├── monitor_repository.py
│   │   ├── price_check_repository.py
│   │   └── notification_repository.py
│   │
│   ├── services/
│   │   ├── monitor_service.py
│   │   ├── price_check_service.py
│   │   ├── notification_service.py
│   │   └── parser_resolver.py
│   │
│   ├── parsers/
│   │   ├── base.py
│   │   ├── result.py
│   │   ├── exceptions.py
│   │   ├── ozon.py
│   │   ├── wildberries.py
│   │   ├── yandex_market.py
│   │   └── registry.py
│   │
│   ├── notifications/
│   │   ├── base.py
│   │   ├── email.py
│   │   ├── telegram.py
│   │   ├── webhook.py
│   │   └── registry.py
│   │
│   ├── workers/
│   │   ├── arq_settings.py
│   │   ├── tasks.py
│   │   └── context.py
│   │
│   ├── scheduler/
│   │   ├── periodic.py
│   │   └── enqueue.py
│   │
│   ├── infra/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── redis.py
│   │   ├── http.py
│   │   └── db/
│   │       ├── base.py
│   │       ├── session.py
│   │       ├── models/
│   │       │   ├── monitor.py
│   │       │   ├── price_check.py
│   │       │   └── notification.py
│   │       └── types.py
│   │
│   └── common/
│       ├── pagination.py
│       ├── clock.py
│       └── ids.py
│
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docker/
│   ├── backend.Dockerfile
│   └── worker.Dockerfile
│
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
├── .env.example
└── README.md
```

## 3. Ответственность каждого модуля

### `api`

HTTP-слой. Здесь находятся:

- FastAPI routers;
- зависимости;
- авторизация, если появится;
- DTO запросов и ответов;
- маппинг доменных ошибок в HTTP-коды.

DTO хранить здесь:

```text
app/api/v1/schemas/
```

Примеры DTO:

- `MonitorCreateRequest`
- `MonitorResponse`
- `PriceCheckResponse`
- `NotificationChannelResponse`

Route handler не должен содержать SQL-запросы, парсинг маркетплейсов или бизнес-решения. Он вызывает service/use case.

### `domain`

Чистые бизнес-сущности и правила. Этот слой не должен зависеть от FastAPI, SQLAlchemy, Redis, httpx или Arq.

Здесь находятся:

- entities: `Monitor`, `PriceCheck`, `Notification`;
- value objects: `Money`, `ProductUrl`;
- enums: `MonitorStatus`, `CheckStatus`, `Marketplace`, `NotificationStatus`;
- domain exceptions.

Важно: ORM-модель не является domain entity. ORM-модели живут в `infra/db/models`.

### `repositories`

Слой доступа к данным. Сервисы не должны знать SQLAlchemy-запросы напрямую.

Здесь находятся:

- интерфейсы репозиториев;
- реализации репозиториев через SQLAlchemy async;
- методы чтения и записи агрегатов.

Рекомендуемый стиль интерфейса:

```python
from typing import Protocol

class MonitorRepositoryProtocol(Protocol):
    async def get_by_id(self, monitor_id: int):
        ...

    async def create(self, data):
        ...
```

### `services`

Use cases приложения. Этот слой координирует domain, repositories, parsers, notifications и очередь задач.

Примеры сервисов:

- `MonitorService.create_monitor`
- `PriceCheckService.run_check`
- `NotificationService.send`
- `ParserResolver.resolve_by_url`

Сервисы должны содержать бизнес-сценарии, но не должны зависеть от FastAPI request/response объектов.

### `infra`

Техническая инфраструктура.

Здесь находятся:

- `config.py` - настройки через Pydantic Settings;
- `logging.py` - настройка логирования;
- `redis.py` - Redis pool/client;
- `http.py` - фабрика httpx-клиента;
- `db/session.py` - async engine и sessionmaker;
- `db/base.py` - declarative base / metadata;
- `db/models/` - ORM-модели SQLAlchemy;
- `db/types.py` - кастомные типы БД при необходимости.

ORM-модели хранить здесь:

```text
app/infra/db/models/
```

Миграции Alembic хранить здесь:

```text
alembic/versions/
```

### `parsers`

Адаптеры получения цены по ссылке. Каждый маркетплейс получает отдельную реализацию.

Парсер:

- определяет, поддерживает ли он URL;
- загружает страницу/API через httpx;
- извлекает цену, название, доступность;
- возвращает нормализованный результат.

Парсер не должен:

- писать в БД;
- отправлять уведомления;
- менять состояние монитора;
- знать про FastAPI.

### `notifications`

Адаптеры доставки уведомлений.

Примеры реализаций:

- `TelegramNotificationSender`
- `EmailNotificationSender`
- `WebhookNotificationSender`

Для MVP можно начать с одного канала, но интерфейс лучше заложить сразу.

### `workers`

Фоновые задачи Arq.

Примеры задач:

- `run_monitor_check(monitor_id)`
- `run_due_monitor_checks()`
- `send_notification(notification_id)`

Worker должен поднимать собственный async DB session, Redis и HTTP-клиенты через worker context.

### `scheduler`

Планирование регулярных проверок.

Для MVP использовать Arq cron:

```text
every 60 sec:
  find monitors where next_check_at <= now
  enqueue run_monitor_check(monitor_id)
  update next_check_at
```

Scheduler не должен жить внутри FastAPI-процесса как бесконечный `while True`.

### `common`

Небольшие общие утилиты без бизнес-логики:

- pagination;
- clock/time helpers;
- id helpers;
- shared primitives.

Не превращать `common` в свалку. Если код относится к бизнесу, он должен быть в `domain` или `services`.

## 4. Паттерн для парсеров

Использовать интерфейс + реализации под конкретные маркетплейсы + registry/resolver.

Интерфейс:

```python
from typing import Protocol

from app.domain.enums import Marketplace
from app.parsers.result import ParsedProduct

class ProductParser(Protocol):
    marketplace: Marketplace

    def supports(self, url: str) -> bool:
        ...

    async def parse(self, url: str) -> ParsedProduct:
        ...
```

Результат парсинга:

```python
from decimal import Decimal
from pydantic import BaseModel

class ParsedProduct(BaseModel):
    title: str | None = None
    price: Decimal
    currency: str = "RUB"
    availability: bool | None = None
    raw_url: str
```

Registry:

```python
class ParserRegistry:
    def __init__(self, parsers: list[ProductParser]):
        self._parsers = parsers

    def resolve(self, url: str) -> ProductParser:
        for parser in self._parsers:
            if parser.supports(url):
                return parser
        raise UnsupportedMarketplaceError(url)
```

Для MVP можно сделать реализации:

- `OzonParser`
- `WildberriesParser`
- `YandexMarketParser`

Если маркетплейс имеет публичный или внутренний JSON endpoint, предпочитать структурированный источник HTML-парсингу. Regex-парсинг HTML использовать только как последний вариант.

## 5. Выбор фоновых задач

Выбран Arq.

Процессы в Docker Compose:

```text
api       -> uvicorn app.main:app
worker    -> arq app.workers.arq_settings.WorkerSettings
mariadb   -> database
redis     -> queue/cache
```

Задачи:

```python
async def run_monitor_check(ctx, monitor_id: int) -> None:
    ...

async def run_due_monitor_checks(ctx) -> None:
    ...

async def send_notification(ctx, notification_id: int) -> None:
    ...
```

Arq cron можно использовать для регулярного поиска due-мониторов:

```python
from arq import cron

class WorkerSettings:
    functions = [
        run_monitor_check,
        run_due_monitor_checks,
        send_notification,
    ]
    cron_jobs = [
        cron(run_due_monitor_checks, minute={0, 1, 2, 3, 4, 5}),
    ]
```

В реальном коде cron лучше настроить проще и явно, например раз в минуту, согласно возможностям версии Arq.

## 6. Потоки данных

### Create monitor

```text
Client
  -> POST /api/v1/monitors
  -> API schema validation
  -> MonitorService.create_monitor
  -> ParserResolver.resolve_by_url
  -> optional first parse / validation
  -> MonitorRepository.create
  -> enqueue initial check
  -> response MonitorResponse
```

Что сохранять в monitor:

- `url`
- `marketplace`
- `target_price`, если пользователь задал
- `check_interval_seconds`
- `status`
- `last_price`
- `last_checked_at`
- `next_check_at`
- `notification_channel`

### Run check

```text
Arq worker
  -> run_monitor_check(monitor_id)
  -> MonitorRepository.get_by_id
  -> ParserResolver.resolve_by_url
  -> parser.parse(url) через httpx
  -> PriceCheckRepository.create
  -> MonitorRepository.update last_price / last_checked_at / next_check_at
  -> PriceCheckService decides if notification is needed
  -> enqueue send_notification(notification_id)
```

Проверка должна:

- писать successful и failed checks;
- использовать retry с backoff для сетевых ошибок;
- не падать навсегда из-за одной ошибки парсинга;
- ограничивать параллельность запросов к маркетплейсам;
- сохранять причину ошибки в истории проверок.

### Send notification

```text
PriceCheckService
  -> condition matched: price <= target_price or price changed
  -> NotificationRepository.create pending notification
  -> enqueue send_notification(notification_id)

Arq worker
  -> NotificationService.send
  -> NotificationSender.send
  -> update notification status: sent / failed
```

Уведомление лучше делать отдельной задачей, а не отправлять прямо внутри проверки цены. Так проще ретраить доставку независимо от парсинга.

## 7. Конфиги, secrets, логирование

`.env.example`:

```env
APP_ENV=local
APP_DEBUG=true
APP_NAME=price-monitor

DATABASE_URL=mysql+asyncmy://app:app@mariadb:3306/app?charset=utf8mb4
REDIS_URL=redis://redis:6379/0

HTTP_TIMEOUT_SECONDS=15
HTTP_MAX_CONNECTIONS=100

CHECK_DEFAULT_INTERVAL_SECONDS=3600
CHECK_BATCH_SIZE=100
CHECK_MAX_RETRIES=3

TELEGRAM_BOT_TOKEN=
EMAIL_SMTP_HOST=
EMAIL_SMTP_PORT=
EMAIL_SMTP_USER=
EMAIL_SMTP_PASSWORD=

LOG_LEVEL=INFO
```

Настройки:

- использовать `pydantic-settings`;
- держать один `Settings` class в `app/infra/config.py`;
- `.env` не коммитить;
- `.env.example` коммитить;
- secrets не хранить в коде;
- в production использовать secret manager, Docker secrets или Kubernetes secrets.

Логирование:

- JSON logs в production;
- human-readable logs локально;
- request id / correlation id для API;
- добавлять в логи `monitor_id`, `check_id`, `marketplace`, `url_host`, `duration_ms`;
- не логировать токены, cookies, passwords и полные headers;
- ошибки парсеров классифицировать: `timeout`, `blocked`, `unsupported_markup`, `invalid_price`, `network_error`.

## 8. Ошибки, которых надо избегать

1. Смешивать FastAPI, SQLAlchemy и бизнес-логику в одном route handler.
2. Делать парсеры, которые сами пишут в БД или отправляют уведомления.
3. Хранить ORM-модели как domain entities.
4. Запускать регулярные проверки внутри FastAPI-процесса через бесконечный loop.
5. Не ограничивать concurrency парсеров.
6. Не сохранять failed checks.
7. Делать один универсальный regex-parser для всех сайтов.
8. Использовать `float` для денег. Использовать только `Decimal`.
9. Отправлять уведомления синхронно в API-запросе.
10. Не проектировать retry/backoff.
11. Прятать настройки по коду вместо `Settings`.
12. Не закладывать idempotency фоновых задач.
13. Делать `common` свалкой для всего подряд.
14. Связывать workers с FastAPI dependency injection напрямую.
15. Логировать чувствительные данные.

## 9. Рекомендации для первой реализации MVP

Начать с PostgreSQL, Redis, Arq, FastAPI и одного-двух парсеров.

Минимальные сущности:

- `monitors`
- `price_checks`
- `notifications`

Минимальные API endpoints:

- `POST /api/v1/monitors`
- `GET /api/v1/monitors`
- `GET /api/v1/monitors/{monitor_id}`
- `POST /api/v1/monitors/{monitor_id}/checks`
- `GET /api/v1/monitors/{monitor_id}/checks`

Первый production-like контур:

- API процесс;
- worker процесс;
- Redis;
- PostgreSQL;
- Alembic migrations;
- structured logging;
- `.env.example`;
- docker-compose для локального запуска.
