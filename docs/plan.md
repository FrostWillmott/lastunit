# План реализации

## Context
Репозиторий содержит только каркас: инструменты, CI, правила для агентов, пустой
`FastAPI()` в корневом `main.py`, Vue-заглушка с одним запросом `/api/health`.
Спецификация — `docs/acceptance.md`: сервис ограниченных распродаж, где покупателей больше,
чем товара. План разбивает реализацию на этапы с логическими коммитами, чтобы
история показывала постепенную работу (требование ТЗ), и фиксирует принятые
решения.

Правила игры на каждый коммит: `make check` зелёный (начиная с этапа 0),
`DECISIONS.md` пополняется в том же коммите, где принято решение, README не
отстаёт от кода. Ветка `main` (локально и в origin), коммиты напрямую, пуш
после каждого этапа.

## Принятые решения (2026-09-10, с пользователем)
| Узел | Решение |
|---|---|
| У1 Вход | **Логин и пароль.** Таблица `users(email UNIQUE, password_hash, role)`, argon2, серверные сессии в таблице `sessions` + httpOnly cookie. Роль `shop` даёт доступ к экрану магазина; seed создаёт одного shop-пользователя. |
| У2 Realtime | **SSE** `GET /api/events`, VueUse `useEventSource`. |
| У3 Топология | **Один uvicorn-процесс**: API + планировщик (lifespan task) + in-process broadcaster. LISTEN/NOTIFY и отдельный worker — «следующий заход» в README. |
| У4 Платёжная заглушка | **Отдельный HTTP-сервис** `paystub/` (свой FastAPI, свой Dockerfile, сервис в compose). Исход по номеру карты; «зависание» = статус `pending` до вызова `resolve`. Ответ приходит вебхуком в бэкенд, плюс сверка по расписанию на случай потерянного вебхука. |

Решения без вопроса (по правилам модулей, запишу в DECISIONS):
- **Один источник времени — часы Postgres.** В Python нет `datetime.now()` в
  бизнес-логике и нет `now()` внутри SQL-выражений. Вместо этого `Clock`-протокол:
  боевая реализация один раз на транзакцию делает `SELECT now()` и отдаёт этот
  момент сервису; сервис передаёт его во все запросы параметром `:now`
  (`WHERE starts_at <= :now`, `expires_at = :now + interval`) и возвращает его
  клиенту как `server_now`. Тестовая реализация — `frozen_clock` (testing.md).
  Итог: в проде время одно на транзакцию и одно на все процессы, в тестах оно
  управляемое, а SQL не зависит от того, кто его вызвал. Планировщик тоже берёт
  `:now` из БД. Ruff-правило DTZ или grep в review ловят `datetime.now()`.
- **Остатки**: счётчик `available` на распродаже, атомарный
  `UPDATE sales SET available = available - 1 WHERE id=? AND available > 0 AND starts_at <= :now AND :now < ends_at RETURNING`
  + `CHECK (available >= 0)`. «Продано» и «в корзинах» — производные счётчики по статусам.
- **Деньги**: копейки `BIGINT`. **Время**: только `timestamptz`; клиент считает
  таймер по смещению от `server_now`, чтобы «старт у всех одновременно» не
  зависел от часов браузера.
- **Зависшая оплата и конец распродажи**: по ТЗ зависший заказ ждёт ответа
  заглушки, товар не возвращается. Значит при окончании распродажи очищаются
  только корзины без начатой оплаты; заказы в `pending` остаются до ответа.
  Автотаймаута нет, это записывается в README как осознанное поведение.
- **Простой сервера**: задачи, созревшие во время простоя, выполняются при
  старте (fire late). Записать в README.

## Ожидаемое поведение → тесты (будущая таблица «State» в README)
| # | Ожидаемое поведение | Тест | Слой |
|---|---|---|---|
| 1 | До старта купить нельзя; в момент старта открывается у всех | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed` | unit, frozen clock |
| 2 | Остатки меняются у всех без обновления страницы | `test_stock_event_reaches_second_client` | integration, 2 SSE-клиента |
| 3 | Последнюю единицу двум не продать | `test_last_unit_two_buyers_one_wins` | integration, 2 корутины |
| 4 | Корзина держит 10 минут, потом возврат, все видят | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | integration |
| 5 | Оплата, начатая до истечения, завершается даже если ответ позже | `test_payment_started_before_expiry_completes_after` | integration |
| 6 | Заглушка «зависла»: заказ pending, товар не возвращается и не продаётся дважды; после ответа досчитывается | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook` | integration |
| 7 | Двойное «оплатить»: один заказ, одно списание | `test_double_pay_same_key_one_order` | integration |
| 8 | Одно письмо о заказе | `test_order_email_sent_exactly_once` | integration, outbox |
| 9 | По окончании: непроданное снято, корзины очищены, владельцы уведомлены | `test_sale_end_clears_holds_and_notifies` | integration |
| 10 | Две вкладки | покрывается 2 + store-тест на два события | frontend |

## Этапы и коммиты

### Этап 0 — рабочий каркас бэкенда (2 коммита)
1. `feat(backend): package layout, settings, health route`
   - `main.py` → `app/main.py`; `app/config.py` на pydantic-settings:
     `DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `SECRET_KEY`, `HOLD_MINUTES=10`,
     `PAYSTUB_URL`, `PAYSTUB_WEBHOOK_SECRET`, `SESSION_TTL_DAYS`.
     Поле добавляется только вместе с потребителем (config-hygiene), поэтому в
     этом коммите только те, что уже читаются.
   - pyproject: `dependencies` + `[dependency-groups] dev` (pytest, pytest-asyncio,
     httpx, mypy, pytest-cov). `asyncio_mode = "auto"`, `--cov-fail-under`, mypy strict.
   - `GET /api/health`; `tests/unit/test_config_env_contract.py`.
   - Удалить `test_main.http`.
2. `docs: README with required sections and State table (all "not proven")`
   - Разделы из documentation.md. Упоминание шаблона и модели/инструмента.
     Таблица State ссылается на номера из `docs/acceptance.md`.

### Этап 1 — БД и модель данных (2 коммита)
3. `feat(db): async engine, session dependency, alembic baseline`
   - `app/db.py`, `alembic/` с async env; `tests/integration/conftest.py`
     (реальная БД из compose, транзакция с rollback на тест); раскомментировать
     `services: db` в ci.yml; `make test-integration`.
4. `feat(db): domain tables and constraints`
   - `users`, `sessions(token, user_id, expires_at)`,
     `sales(title, price_minor, quantity, available, starts_at, ends_at, status)`,
     `reservations(sale_id, user_id, status, expires_at, released_at)` с индексом
     `(status, expires_at)`,
     `orders(reservation_id UNIQUE, user_id, sale_id, amount_minor, status, idempotency_key UNIQUE)`,
     `payments(order_id UNIQUE, provider_ref UNIQUE, status, requested_at, resolved_at)`,
     `notifications(kind, entity_id, recipient, payload, sent_at, UNIQUE(kind, entity_id))`.
   - Миграция прочитана вручную; ограничения перечислены в DECISIONS.

### Этап 2 — авторизация (2 коммита)
5. `feat(auth): register, login, logout with server-side sessions`
   - `app/services/auth.py`, `app/routers/auth.py`; argon2 через `pwdlib`;
     `current_user` и `require_shop` зависимости. Unit-тесты на хэш и на
     истёкшую сессию; интеграционный на регистрацию с дублем email → 409.
6. `feat(auth): shop role and seed shop user`
   - `make seed` создаёт shop-пользователя из `.env` (`SEED_SHOP_EMAIL/PASSWORD`).

### Этап 3 — распродажа и удержание (3 коммита)
7. `feat(sales): create/list sales with server time`
   - `GET /api/sales`, `GET /api/sales/{id}` (+`server_now`), `POST /api/sales`
     для роли shop. Unit-тесты статуса по frozen clock (тест 1).
8. `feat(cart): reserve one unit with 10-minute hold`
   - `POST /api/sales/{id}/reserve` → атомарный UPDATE; 409 «закончилось».
     Тест 3 (две корутины на последней единице).
9. `feat(cart): release hold and view my cart`
   - `DELETE /api/reservations/{id}`, `GET /api/me/cart`. Тест на возврат единицы.

### Этап 4 — заказ и платёжная заглушка (4 коммита)
10. `feat(paystub): standalone payment stub service`
    - `paystub/` как отдельный пакет в том же репо: `POST /payments`
      (сумма, карта, `callback_url`) → `approved` / `declined` / `pending` по
      номеру карты; `POST /payments/{ref}/resolve` для зависших;
      `GET /payments/{ref}`. Вебхук в `callback_url` с HMAC-подписью.
      Свой Dockerfile, сервис `paystub` в compose, порт 8001. Unit-тесты заглушки.
      Интеграционные тесты бэкенда поднимают её in-process через httpx ASGI
      transport: реальный HTTP-контракт без сети.
11. `feat(orders): create order with Idempotency-Key`
    - `POST /api/orders` (reservation_id + заголовок). Повтор ключа → тот же
      ответ, вторая строка не создаётся. Тест 7.
12. `feat(payments): pay through paystub, webhook, guarded transitions`
    - `POST /api/orders/{id}/pay` → резервация в `paying`, вызов заглушки,
      статус по ответу. `POST /api/payments/webhook` идемпотентен по
      `provider_ref`; переходы `UPDATE ... WHERE status='pending'`.
      Тест 6 (обе половины).
13. `feat(payments): payment started before hold expiry completes`
    - Резервация в `paying` не трогается планировщиком. Тест 5.

### Этап 5 — планировщик и outbox (3 коммита)
14. `feat(scheduler): expire holds with SKIP LOCKED poll loop`
    - `app/scheduler.py` в lifespan; `FOR UPDATE SKIP LOCKED`; fire late при старте.
      Тест 4 (первая половина).
15. `feat(outbox): notifications, email stub, sender loop`
    - `app/email_stub.py` пишет в лог и `sent_at`. Письмо о заказе в той же
      транзакции, что `paid`. Тест 8.
16. `feat(sales): end-of-sale cleanup and payment reconciliation`
    - `ends_at <= :now` → снять непроданное, очистить корзины без оплаты,
      уведомить владельцев. Сверка `pending` платежей с заглушкой раз в N секунд.
      Тест 9.

### Этап 6 — live-обновления (2 коммита)
17. `feat(realtime): SSE endpoint and in-process broadcaster`
    - `app/realtime.py`, `GET /api/events`; события `stock_changed`,
      `sale_status`, `order_status`. Публикация после commit из тех же мест,
      где пишется outbox.
18. `test(realtime): two clients see the same stock change`
    - Тест 2 и тест 4 (вторая половина).

### Этап 7 — фронтенд (6 коммитов)
19. `feat(frontend): router, pinia, typed api client, auth screens`
    - Добавить `vue-router`, `pinia`, `@vueuse/core`; `src/api/` по типам бэкенда;
      формы регистрации и входа; guard маршрутов по роли.
20. `feat(frontend): storefront with stock and countdown`
    - `useRealtime()`; store `sales`; таймер по `server_now`; кнопка «в корзину»
      заблокирована до старта.
21. `feat(frontend): cart and checkout`
    - Таймер удержания; «оплатить» с Idempotency-Key и блокировкой на время
      запроса; поле карты с подсказкой тестовых номеров.
22. `feat(frontend): buyer cabinet` — заказы и статусы, обновление по SSE.
23. `feat(frontend): shop dashboard` — остатки, продано, в корзинах, выручка;
    создание распродажи; список зависших платежей со ссылкой на resolve заглушки.
24. `test(frontend): store applies two realtime events` — половина «двух вкладок».

### Этап 8 — сдача (2 коммита)
25. `feat: seed sale and compose smoke run`
    - `make seed` добавляет распродажу «старт через 1 минуту, 5 штук».
      Прогон `make up` с чистого `.env` по README.
26. `docs: final State table, next steps, session exports`
    - README: реальные статусы всех строк; «Next steps» (LISTEN/NOTIFY, worker,
      таймаут зависших платежей, пагинация); `agent-sessions/` с экспортами.

Итого 26 коммитов, 9 этапов. Пуш в GitHub после каждого этапа.

## Проверка
- Каждый коммит: `make check`. Интеграционные тесты: `docker compose up -d db`
  и `make test-integration`.
- После этапа 7: `make up` с нуля, два окна браузера (обычное и приватное, два
  покупателя), ручной прогон сценариев 1, 3, 4, 6, 7; зависание проверяется
  картой `…9995` и кнопкой resolve на `localhost:8001/docs`.
- Перед сдачей: `make ci`, `make audit`, `make docker-build`.

## Критичные файлы
- Есть: `Makefile`, `docker-compose.yml`, `Dockerfile`, `.github/workflows/ci.yml`
  (раскомментировать db), `frontend/vite.config.ts` (proxy `/api`),
  `frontend/nginx.conf`, `frontend/src/api.ts` (станет `src/api/`).
- Появятся: `app/{main,config,db,scheduler,realtime,email_stub}.py`,
  `app/{models,routers,services}/`, `alembic/`, `paystub/`, `tests/{unit,integration}/`.
