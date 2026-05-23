# URL Normalization

Модуль: `app.domain.url_normalization`.

## Правила MVP

Общие правила:

- парсим URL через `urllib.parse`, а не через одну большую регулярку;
- принимаем только `http` и `https`, в канон приводим к `https`;
- не принимаем URL с credentials (`user:password@host`);
- определяем marketplace только по allowlist host;
- не ходим по redirect-ссылкам и не раскрываем short links;
- для карточек товара удаляем query string и fragment целиком;
- возвращаем `original_url`, `normalized_url`, `marketplace`, `is_supported`,
  `reason_if_invalid`.

Поддержанные карточки:

- Ozon: `ozon.ru`, `www.ozon.ru`, `m.ozon.ru`; path `/product/<slug-with-id>/`.
- Wildberries: `wildberries.ru`, `www.wildberries.ru`, `m.wildberries.ru`; path
  `/catalog/<numeric-id>/detail.aspx`.
- Yandex Market: `market.yandex.ru`, `www.market.yandex.ru`, `m.market.yandex.ru`; path
  `/product--<slug>/<numeric-id>`.

Отбрасываемые URL:

- поиск, категории, профили, кабинеты продавцов, рекламные/redirect paths;
- неподдержанные домены, включая short-link domain `wb.ru`;
- похожие host вроде `ozon.ru.evil.example`;
- ссылки без числового product id в ожидаемом месте.

## Edge Cases

- `http` карточка нормализуется в `https`.
- `www`/`m` host нормализуются в канонический host магазина.
- `utm_*`, `from`, `src`, `sku`, `clid`, `uniqueId`, `targetUrl`, `advert` и другие query params
  удаляются вместе с query string.
- Fragment вроде `#reviews` удаляется.
- Окружающие пробелы не попадают в `original_url`.
- `wb.ru` намеренно не поддержан в MVP, потому что это redirect/short-link домен.
- Variant-level параметры (`sku`, `size`) сейчас не сохраняются: MVP нормализует product-card URL,
  а не конкретный оффер/размер.

## Extension Strategy

1. Добавить новый `Marketplace` enum value.
2. Добавить `MarketplaceUrlRule` в `_RULES`: allowlist host, canonical host, функцию нормализации path.
3. В функции нормализации path сначала разбирать segments, затем применять небольшие проверки id/slug.
4. Решить, какие query params являются семантическими для цены/варианта, и сохранять только их.
5. Добавить unit tests: валидная карточка, мусорные query params, поиск/категория, redirect, похожий host.
6. Подключить parser `supports()` через `normalize_product_url`, чтобы API и парсеры делили одни правила.
