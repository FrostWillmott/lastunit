# План реализации

## Context
Репозиторий стартовал с каркаса (инструменты, CI, правила для агентов, пустой
`FastAPI()` в корневом `main.py`, Vue-заглушка с одним запросом `/api/health`).
Этап 0 выполнен: бэкенд — пакет `app/` с фабрикой `create_app()`, `GET /api/health`
и юнит-тестами; `make check` зелёный.
Спецификация — `docs/acceptance.md`: сервис ограниченных распродаж, где покупателей больше,
чем товара. План разбивает реализацию на этапы с логическими коммитами, чтобы
история показывала постепенную работу (требование ТЗ), и фиксирует принятые
решения.

Правила игры на каждый коммит: `make check` зелёный (начиная с этапа 0),
`DECISIONS.md` пополняется в том же коммите, где принято решение, README не
отстаёт от кода. Ветка `main` (локально и в origin), коммиты напрямую, пуш
после каждого этапа.

Ревизия 2026-09-10: план прошёл независимый аудит второй моделью
(`docs/plan-audit-2026-09-10.md`); правки ниже закрывают его находки и ответы
пользователя. Решения записаны в `DECISIONS.md` той же датой.

Что диктуют модули `.claude/rules/`, здесь не повторяется: инварианты в БД,
идемпотентность, outbox, `SKIP LOCKED`, UTC и `timestamptz`, деньги в `BIGINT`,
структура тестов и таблица State — `transactional-web.md`, `testing.md`,
`config-hygiene.md`, `documentation.md`. Ниже только то, что модули оставляют
на выбор проекта.

## Принятые решения (2026-09-10, с пользователем; подробности в `DECISIONS.md`)
| Узел | Решение |
|---|---|
| У1 Вход | **Логин и пароль.** `users(email UNIQUE, password_hash, role)`; пароли — argon2id через `pwdlib`. Серверные сессии: токен `secrets.token_urlsafe(32)`, в таблице `sessions` его SHA-256, cookie HttpOnly + SameSite=Lax, Secure по `APP_ENV`. Подписи нет, `SECRET_KEY` не нужен. Роль `shop` даёт доступ к экрану магазина; seed создаёт одного shop-пользователя. |
| У2 Realtime | **SSE** `GET /api/events`, VueUse `useEventSource`. |
| У3 Топология | **Один uvicorn-процесс**: API + планировщик (lifespan task) + in-process broadcaster. LISTEN/NOTIFY и отдельный worker — «следующий заход» в README. |
| У4 Платёжная заглушка | **Отдельный HTTP-сервис** `paystub/` (свой FastAPI, свой Dockerfile, сервис в compose). Исход по номеру карты; «зависание» = статус `pending` до вызова `resolve`. Ответ приходит вебхуком; заглушка повторяет недоставленный вебхук. Автоматической сверки нет: на экране магазина кнопка «проверить статус», которая спрашивает заглушку и применяет ответ тем же обработчиком, что и вебхук. |
| У5 Платежи как попытки | Заказ один на резервацию; `payments` — попытки оплаты, одновременно не больше одной в `pending` (partial UNIQUE). Отклонённая попытка оставляет резервацию (`paying → held`, `expires_at` прежний) и заказ (`pending`) до истечения удержания; повтор — новая попытка на том же заказе. |
| У6 Лимит на покупателя | Одна активная резервация на покупателя на распродажу: partial UNIQUE `(sale_id, user_id) WHERE status IN ('held','paying')`. |
| У7 Оплата после истечения | Срок проверяется в самом переходе `held → paying`: `UPDATE ... WHERE status='held' AND expires_at > :now AND :now < ends_at`. Ноль строк → 409. От интервала планировщика поведение не зависит. |
| У8 «Зависла» | И ответ `pending`, и HTTP-таймаут заглушки: оба оставляют попытку и заказ в `pending`, товар удержан. Демо показывает первое через номер карты. |
| У9 Покрытие фронтенда | Порог считается только по `src/stores` и `src/api` (`coverage.include`, обоснование комментарием в `vite.config.ts`); компоненты и экраны в порог не входят. |

Решения по месту (тоже в `DECISIONS.md`):
- **Один источник времени — часы Postgres.** В Python нет `datetime.now()` в
  бизнес-логике и нет `now()` внутри SQL-выражений (включая `server_default=func.now()`
  в моделях). Вместо этого `Clock`-протокол: боевая реализация один раз на транзакцию
  делает `SELECT now()` и отдаёт этот момент сервису; сервис передаёт его во все
  запросы параметром `:now` (`WHERE starts_at <= :now`, `expires_at = :now + interval`)
  и возвращает его клиенту как `server_now`. Тестовая реализация — `frozen_clock`
  (`testing.md`). `Clock` попадает в приложение через фабрику `create_app(clock=...)`,
  которой пользуются и планировщик, и SSE. Клиент считает таймеры по смещению от
  `server_now`, чтобы «старт у всех одновременно» не зависел от часов браузера.
  Механическая проверка: `tests/unit/test_no_local_time.py` grep'ом ищет
  `datetime.now`, `datetime.utcnow`, `func.now`, `time.time`, `date.today` в
  `app/` и падает на любом вхождении (Ruff DTZ для этого не годится: его нет в
  `select`, и `datetime.now(UTC)` он пропускает). Голый `now()` намеренно не
  запрещён — Clock реализует `SELECT now()`.
- **Время распродажи абсолютное, в IANA-зоне магазина.** `sales.timezone`
  (имя IANA) — колонка; `POST /api/sales` берёт `timezone` + локальные
  `starts_at`/`ends_at`, нормализует в UTC через `ZoneInfo` и хранит `timestamptz`.
  Покупатели видят только отсчёт от `server_now`, зона им не нужна (колонки на
  `users` нет). `ZoneInfo` в grep-проверку источника времени не попадает.
- **Остатки**: счётчик `available` на распродаже, атомарный
  `UPDATE sales SET available = available - 1 WHERE id=? AND available > 0 AND starts_at <= :now AND :now < ends_at RETURNING`
  + `CHECK (available >= 0)`. «Продано» и «в корзинах» — производные счётчики по статусам.
- **Зависшая оплата и конец распродажи**: по ТЗ зависший заказ ждёт ответа
  заглушки, товар не возвращается. При окончании распродажи очищаются только
  корзины в `held`; резервации в `paying` остаются до ответа. Отклонение после
  `ends_at` переводит резервацию в `cleared`, а не в `held`: товар на витрину не
  возвращается. Автотаймаута нет, это записывается в README как осознанное поведение.
- **Простой сервера**: задачи, созревшие во время простоя, выполняются при
  старте (fire late). Записать в README.
- **`HOLD_MINUTES = 10`** — константа в `app/services/cart.py`, не настройка:
  ТЗ фиксирует значение, ручку крутить некому.

## Машины состояний
Определяются enum'ами в коммите 4; каждый переход — `UPDATE ... WHERE status=<from>`
с проверкой rowcount, ноль строк → 409 или no-op.

| Сущность | Статусы | Переходы |
|---|---|---|
| `sales` | `active` \| `ended` | хранится только терминальный `ended` (ставит планировщик при `ends_at <= :now`). «Ещё не началась / идёт» выводится из `starts_at`, `ends_at` и `:now`, в API — вычисляемое поле `phase`. |
| `reservations` | `held` → `paying` → `sold`; `held` → `expired` (планировщик, 10 мин); `held` → `released` (покупатель); `held` → `cleared` (конец распродажи); `paying` → `held` (попытка отклонена до `ends_at`); `paying` → `cleared` (отклонена после `ends_at`) | `expired`, `released` и `cleared`-из-`held` возвращают единицу в `available` в той же транзакции; `cleared`-из-`paying` — нет (распродажа закончилась). |
| `orders` | `pending` → `paid`; `pending` → `cancelled` | один заказ на резервацию (`reservation_id UNIQUE`), создаётся по Idempotency-Key. `cancelled` ставится вместе с `expired`/`released`/`cleared` резервации. Отклонённая попытка заказ не меняет (У5). |
| `payments` | `pending` → `approved` \| `declined` | попытка на заказ; partial UNIQUE `(order_id) WHERE status='pending'`; `provider_ref` генерирует бэкенд до вызова заглушки. Результат применяет одна функция `apply_payment_result(provider_ref, outcome, now)` — из синхронного ответа, вебхука и кнопки «проверить статус». |

## Ожидаемое поведение → тесты (будущая таблица «State» в README)
Номера — из `docs/acceptance.md`; «две вкладки» — требование 11 того же файла.

| # | Ожидаемое поведение | Тест | Слой |
|---|---|---|---|
| 1 | До старта купить нельзя; в момент старта открывается у всех | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed`. «У всех одновременно» отдельного теста не имеет: клиент считает таймер от `server_now`, в State — «partially proven» | integration, frozen clock |
| 2 | Остатки меняются у всех без обновления страницы | `test_stock_event_reaches_second_client` (broadcaster + генератор SSE), `test_sse_smoke_real_server` (uvicorn) | integration |
| 3 | Последнюю единицу двум не продать | `test_last_unit_two_buyers_one_wins` | integration, 2 корутины, 2 соединения |
| 4 | Корзина держит 10 минут, потом возврат, все видят | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | integration |
| 5 | Оплата, начатая до истечения, завершается даже если ответ позже | `test_payment_started_before_expiry_completes_after` | integration |
| 6 | Заглушка «зависла»: заказ pending, товар не возвращается и не продаётся дважды; после ответа досчитывается | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | integration |
| 7 | Двойное «оплатить»: один заказ, одно списание | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | integration |
| 8 | Одно письмо о заказе | `test_order_email_sent_exactly_once` | integration, outbox |
| 9 | По окончании: непроданное снято, корзины очищены, владельцы уведомлены | `test_sale_end_clears_holds_and_notifies` | integration |
| Т11 | Две вкладки | покрывается 2 + store-тест на два события + тест fan-out `useRealtime` | frontend |
| — | Отклонённая попытка возвращает товар в корзину, заказ жив (У5) | `test_declined_attempt_returns_reservation_to_cart` | integration |
| — | «Проверить статус» применяет ответ как вебхук (У4) | `test_check_status_applies_result_like_webhook` | integration |

## Этапы и коммиты

### Этап 0 — рабочий каркас бэкенда (2 коммита)
1. `feat(backend): package layout, settings, health route`
   - `main.py` → `app/main.py` с фабрикой `create_app(clock=..., broadcaster=...)`;
     `app/config.py` на pydantic-settings. По `config-hygiene.md` поле добавляется
     только вместе с потребителем, поэтому здесь только `APP_ENV` и `LOG_LEVEL`.
     Остальные появляются в коммитах-потребителях: `DATABASE_URL` (3),
     `SESSION_TTL_DAYS` (5), `SEED_SHOP_EMAIL/PASSWORD` (6), `PAYSTUB_URL`,
     `PAYSTUB_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` (12). `SECRET_KEY` нет (У1).
   - pyproject: `dependencies` + `[dependency-groups] dev` (pytest, pytest-asyncio,
     httpx, mypy, pytest-cov). `asyncio_mode = "auto"`, mypy strict. Порог
     `--cov-fail-under` включается в коммите 5, когда появляется первый реальный
     набор тестов (`testing.md`, раздел Coverage).
   - `GET /api/health`; `tests/unit/test_config_env_contract.py`;
     `tests/unit/test_no_local_time.py` (grep-проверка источника времени).
   - Удалить `test_main.http`.
2. `docs: README with required sections and State table (all "not proven")`
   - Разделы из `documentation.md`. Упоминание шаблона и модели/инструмента.
     Таблица State ссылается на номера из `docs/acceptance.md`.

### Этап 1 — БД и модель данных (2 коммита)
3. `feat(db): async engine, session dependency, alembic baseline`
   - `app/db.py`, `alembic/` с async env; `tests/integration/conftest.py`:
     реальная БД из compose, **TRUNCATE всех таблиц перед каждым тестом, настоящие
     commit** — тесты на гонки (3, 4, 5, 6) и SSE после commit требуют отдельных
     соединений, rollback-на-тест их ломает. `get_db` в тестах отдаёт обычные
     сессии из пула.
   - Раскомментировать `services: db` в ci.yml и добавить `env: DATABASE_URL`
     в job backend (`.env` в CI нет).
   - Makefile: `make test` = unit + integration (требует поднятой БД),
     `make test-unit`, `make test-integration`. README: «`make check` требует
     `docker compose up -d db`».
   - Docker: entrypoint бэкенда выполняет `alembic upgrade head` перед uvicorn,
     чтобы `make up` с чистого `.env` давал рабочее приложение.
4. `feat(db): domain tables, enums and constraints`
   - `users`, `sessions(token_hash UNIQUE, user_id, expires_at)`,
     `sales(title, price_minor, quantity, available, starts_at, ends_at, timezone, status)`
     с `CHECK (available >= 0)`, `CHECK (starts_at < ends_at)`, индексом `(status, ends_at)`,
     `reservations(sale_id, user_id, status, expires_at, released_at)` с индексом
     `(status, expires_at)` и partial UNIQUE `(sale_id, user_id) WHERE status IN ('held','paying')` (У6),
     `orders(reservation_id UNIQUE, user_id, sale_id, amount_minor, status, idempotency_key, UNIQUE(user_id, idempotency_key))`,
     `payments(order_id, provider_ref UNIQUE, status, requested_at, resolved_at)`
     с partial UNIQUE `(order_id) WHERE status='pending'` (У5),
     `notifications(kind, entity_id, recipient, payload, sent_at, UNIQUE(kind, entity_id))`.
   - Enum'ы статусов и таблица переходов из раздела «Машины состояний» —
     в `app/models/enums.py`, один источник для всех последующих коммитов.
   - Миграция прочитана вручную; ограничения перечислены в DECISIONS.

### Этап 2 — авторизация (2 коммита)
5. `feat(auth): register, login, logout with server-side sessions`
   - `app/services/auth.py`, `app/routers/auth.py`; argon2id через `pwdlib`;
     токен сессии `secrets.token_urlsafe(32)`, в БД SHA-256, cookie HttpOnly,
     SameSite=Lax, Secure при `APP_ENV != "dev"` (У1); `current_user` и
     `require_shop` зависимости. Unit-тесты на хэш и на истёкшую сессию;
     интеграционный на регистрацию с дублем email → 409.
     Здесь включается `--cov-fail-under` на достигнутом числе.
6. `feat(auth): shop role and seed shop user`
   - `make seed` создаёт shop-пользователя из `.env` (`SEED_SHOP_EMAIL/PASSWORD`);
     entrypoint из коммита 3 вызывает seed после миграций (идемпотентно).

### Этап 3 — распродажа и удержание (3 коммита)
7. `feat(sales): create/list sales with server time`
   - `GET /api/sales`, `GET /api/sales/{id}` (+`server_now`, `phase`), `POST /api/sales`
     для роли shop (`available = quantity` при создании). `POST` принимает
     `timezone` (IANA) и локальные `starts_at`/`ends_at`; бэкенд нормализует их
     в UTC через `zoneinfo.ZoneInfo` и хранит `timestamptz` + `timezone` для показа.
     Unit-тесты чистой функции `phase(starts_at, ends_at, now)` и перевода
     локального времени в UTC, включая границу DST; тест 1 живёт в коммите 8,
     потому что запрет до старта — условие в SQL, а не в Python.
8. `feat(cart): reserve one unit with 10-minute hold`
   - `POST /api/sales/{id}/reserve` → атомарный UPDATE; 409 «закончилось» /
     «ещё не началось» / «уже в корзине» (У6). Тест 3 (две корутины, два
     соединения, последняя единица) и тест 1 (обе половины, frozen clock).
   - `app/realtime.py`: интерфейс `Broadcaster` с no-op реализацией, передаётся в
     `create_app`; сервис публикует `stock_changed` после commit уже здесь, чтобы
     коммит 18 не переписывал пять модулей.
9. `feat(cart): release hold and view my cart`
   - `DELETE /api/reservations/{id}` (`held → released`, заказ, если есть, →
     `cancelled`), `GET /api/me/cart`. Тест на возврат единицы.

### Этап 4 — заказ и платёжная заглушка (5 коммитов)
10. `feat(paystub): standalone payment stub service`
    - `paystub/` как отдельный пакет в том же репо: `POST /payments`
      (`reference` от бэкенда, сумма, карта, `callback_url`) → `approved` /
      `declined` / `pending` по номеру карты; `POST /payments/{ref}/resolve` для
      зависших; `GET /payments/{ref}` — статус для кнопки «проверить статус».
      Вебхук в `callback_url` с HMAC-подписью; при не-2xx или таймауте заглушка
      повторяет доставку (3 попытки с растущей паузой, состояние в памяти).
      Таблица карт фиксируется здесь и в README:
      `…0000` approved, `…0002` declined, `…9995` pending.
    - Исходящий HTTP-клиент заглушки инжектируется (`create_app(http_client=...)`),
      чтобы в интеграционных тестах бэкенда вебхук шёл на ASGI-приложение
      бэкенда in-process: реальный HTTP-контракт без сети.
    - Свой Dockerfile, сервис `paystub` в compose, порт 8001; `known-first-party`
      в `ruff.toml` дополняется `paystub`. Unit-тесты заглушки, включая повтор вебхука.
11. `feat(orders): create order with Idempotency-Key`
    - `POST /api/orders` (reservation_id + заголовок). Ключ уникален в паре с
      `user_id`; повтор ключа → тот же ответ, вторая строка не создаётся;
      параллельный дубль ловится по `IntegrityError` и перечитывается.
      `amount_minor` — снимок цены. Тест 7 (первая половина).
12. `feat(payments): pay through paystub, webhook, guarded transitions`
    - `POST /api/orders/{id}/pay`. Порядок шагов зафиксирован, это и есть
      гарантия: (1) одна транзакция — `reservations held→paying` с проверкой
      `expires_at > :now AND :now < ends_at` (У7), INSERT попытки в `payments` с
      `provider_ref`, сгенерированным бэкендом, заказ остаётся `pending`;
      commit; (2) вызов заглушки с `reference = provider_ref` и
      `callback_url = PUBLIC_BASE_URL + /api/payments/webhook`; (3) синхронный
      `approved`/`declined` применяется через `apply_payment_result`; `pending`
      и таймаут ничего не меняют (У8). Второй клик упирается в partial UNIQUE
      на `pending`-попытку до любого HTTP.
    - `POST /api/payments/webhook`: проверка HMAC, затем `apply_payment_result`:
      `UPDATE payments ... WHERE provider_ref=? AND status='pending'`; только при
      rowcount = 1 в той же транзакции: `approved` → `orders paid`,
      `reservations paying→sold`; `declined` → `reservations paying→held`
      (или `cleared`, если `ends_at <= :now`), заказ не меняется (У5).
    - Настройки `PAYSTUB_URL`, `PAYSTUB_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`
      (адрес бэкенда, который заглушка видит из compose-сети).
    - Тесты: 6 (`keeps_stock`, `resolves_via_webhook`, `timeout_keeps_order_pending`),
      7 (`calls_paystub_once`), `declined_attempt_returns_reservation_to_cart`.
13. `feat(scheduler): expire holds with SKIP LOCKED poll loop`
    - `app/scheduler.py` в lifespan; `FOR UPDATE SKIP LOCKED` по `held` с
      `expires_at <= :now`; `expired` + `available + 1` + заказ `cancelled` в одной
      транзакции; fire late при старте. Публичная `run_once(session, now)` — тесты
      зовут её напрямую, без ожидания цикла. Тест 4 (первая половина).
14. `feat(payments): payment started before hold expiry completes`
    - Резервация в `paying` не попадает под `run_once`. Тест 5: reserve при T,
      pay при T+9 (карта `pending`), `run_once(T+11)`, resolve → `sold`.
      Идёт после 13, потому что тест 5 нуждается в механизме истечения.

### Этап 5 — outbox, конец распродажи, экраны (3 коммита)
15. `feat(outbox): notifications, email stub, sender loop`
    - `app/email_stub.py` пишет в лог и `sent_at`. Письмо о заказе
      (`kind='order_paid'`, `entity_id=order_id`) в той же транзакции, что `paid`. Тест 8.
16. `feat(sales): end-of-sale cleanup`
    - `run_once` берёт `sales` с `ends_at <= :now AND status='active'`
      `FOR UPDATE SKIP LOCKED`: `status='ended'`, `available=0`, `held → cleared`
      (заказы → `cancelled`) с уведомлением `kind='cart_cleared'`,
      `entity_id=reservation_id`; `paying` не трогается. Тест 9.
17. `feat(api): shop stats, payment status check, buyer orders`
    - `GET /api/shop/sales/{id}/stats` (остатки, продано, в корзинах, выручка,
      список `pending` попыток с `provider_ref`), `POST /api/shop/payments/{ref}/check`
      (запрос `GET /payments/{ref}` к заглушке → `apply_payment_result`),
      `GET /api/me/orders`. Интеграционные тесты на счётчики после
      reserve/pay/expire и `test_check_status_applies_result_like_webhook`.

### Этап 6 — live-обновления (2 коммита)
18. `feat(realtime): SSE endpoint and in-process broadcaster`
    - `GET /api/events`; боевой `Broadcaster` вместо no-op; события
      `stock_changed`, `sale_status`, `order_status`. Публикация после commit из
      тех же мест, где пишется outbox (планировщик, оплата, вебхук).
19. `test(realtime): two clients see the same stock change`
    - Тест 2 и тест 4 (вторая половина): два подписчика `Broadcaster` + генератор
      SSE, мутация через API, оба получили событие. Плюс один smoke
      `test_sse_smoke_real_server`: uvicorn на свободном порту в отдельной задаче,
      один `httpx`-клиент читает поток (httpx `ASGITransport` буферизует ответ
      целиком, SSE через него не читается).

### Этап 7 — фронтенд (6 коммитов)
Каждый коммит несёт тесты для своего store/api-модуля: порог покрытия считается
по `src/stores` и `src/api` (У9), и `make check` должен оставаться зелёным.
20. `feat(frontend): router, pinia, typed api client, auth screens`
    - Добавить `vue-router`, `pinia`, `@vueuse/core`; `src/api/` по типам бэкенда;
      формы регистрации и входа; guard маршрутов по роли. `coverage.include`
      в `vite.config.ts` → `src/stores/**`, `src/api/**` с комментарием-обоснованием.
      Тесты api-клиента.
21. `feat(frontend): storefront with stock and countdown`
    - `useRealtime()`; store `sales`; таймер по `server_now`; кнопка «в корзину»
      заблокирована до старта. Тест store `sales`.
22. `feat(frontend): cart and checkout`
    - Таймер удержания; «оплатить» с Idempotency-Key и блокировкой на время
      запроса; после отклонения — «попробовать снова» (новая попытка); поле карты
      с подсказкой тестовых номеров из коммита 10. Тест store `cart`.
23. `feat(frontend): buyer cabinet` — заказы и статусы, обновление по SSE. Тест store `orders`.
24. `feat(frontend): shop dashboard` — остатки, продано, в корзинах, выручка;
    создание распродажи (пикер даты-времени + выбор IANA-зоны); список зависших
    попыток с кнопкой «проверить статус»
    (коммит 17) и ссылкой на resolve заглушки. Тест store `shop`.
25. `test(frontend): store applies two realtime events` — половина «двух вкладок».

### Этап 8 — сдача (2 коммита)
26. `feat: seed sale and compose smoke run`
    - `make seed` добавляет распродажу «старт через 1 минуту, 5 штук».
      Прогон `make up` с чистого `.env` по README (миграции и seed — entrypoint).
27. `docs: final State table, next steps, session exports`
    - README: реальные статусы всех строк; «Next steps» (LISTEN/NOTIFY, worker,
      таймаут зависших платежей, автоматическая сверка с платёжкой, пагинация);
      `agent-sessions/` с экспортами.

Итого 27 коммитов, 9 этапов. Пуш в GitHub после каждого этапа.

## Проверка
- Каждый коммит: `make check` при поднятой БД (`docker compose up -d db`);
  `make test-unit` без неё.
- После этапа 7: `make up` с нуля, два окна браузера (обычное и приватное, два
  покупателя), ручной прогон сценариев 1, 3, 4, 6, 7; зависание проверяется
  картой `…9995`, затем кнопкой resolve на `localhost:8001/docs` или «проверить
  статус» на экране магазина; отклонение — картой `…0002`.
- Перед сдачей: `make ci`, `make audit`, `make docker-build`.

## Критичные файлы
- Есть: `Makefile`, `docker-compose.yml`, `Dockerfile`, `.github/workflows/ci.yml`
  (раскомментировать db, добавить `DATABASE_URL`), `frontend/vite.config.ts`
  (proxy `/api`, `coverage.include`), `frontend/nginx.conf`, `frontend/src/api.ts`
  (станет `src/api/`), `ruff.toml` (`known-first-party`).
- Появятся: `app/{main,config,db,scheduler,realtime,email_stub}.py`,
  `app/{models,routers,services}/`, `alembic/`, `paystub/`, `tests/{unit,integration}/`,
  entrypoint бэкенда.
