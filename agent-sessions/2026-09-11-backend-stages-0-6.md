# 2026-09-10/11 — реализация бэкенда: этапы 0–6 + два раунда ревью

Инструмент: Claude Code (CLI). Модель: deepseek-v4-pro (не-Anthropic эндпоинт
`api.deepseek.com/anthropic`). Полный экспорт: `2026-09-11-backend-stages-0-6.jsonl`
(снимок на закрытии сессии). Сессия шла с перерывами и продолжалась после сжатия
контекста; в экспорте одна непрерывная лента.

## Что сделано (по этапам плана `docs/plan.md`)

- **Этап 0** — пакет `app/`: `create_app(clock, broadcaster)` + модульный `app`,
  `Settings` (`APP_ENV`, `LOG_LEVEL`), `GET /api/health`, dev-зависимости,
  `test_config_env_contract`, `test_no_local_time`. Ревью-фикс: scope logger,
  time-guard.
- **Этап 1** — БД: async engine + `get_db`, Alembic baseline, таблицы домена с
  инвариантами как ограничениями (`CHECK`, частичные `UNIQUE`, enum-CONSTRAINT,
  `email = lower(email)`), строковые enum в `app/models/enums.py`. Ревью-фикс:
  enum-ограничения, case-insensitive email, изоляция тестовой БД.
- **Этап 2** — auth: регистрация/вход/выход, argon2id через pwdlib, серверные
  сессии (`token_urlsafe(32)` → SHA-256 в БД, HttpOnly+SameSite=Lax), роль shop,
  идемпотентный seed демо-магазина (только вне prod).
- **Этап 3** — sales: создание/список с серверным временем и фазой, времена в
  IANA-зоне магазина → UTC.
- **Этап 4** — cart: резерв одной единицы с 10-минутным холдом (кламп к концу
  распродажи), release, «один активный холд на покупателя на распродажу».
- **Этап 5** — orders + платежи: `Idempotency-Key`, отдельный сервис-заглушка
  `paystub/` с HMAC-вебхуком и ретраями, охраняемые переходы (`held→paying` при
  `expires_at > now`), scheduler (SKIP LOCKED), outbox-уведомления + email-stub,
  завершение распродажи (обнуление стока, очистка холдов).
- **Этап 6** — realtime: SSE `GET /api/events` + in-process broadcaster, тест
  «два клиента видят одно изменение», настройка compose (PAYSTUB_URL/PUBLIC_BASE_URL,
  общий секрет вебхука).

После каждого этапа — `/code-review`; реальные находки исправлены в двух
фикс-коммитах (`9571e31`, `d1fe818`).

## Коммиты сессии (33, `7752cdf..d1fe818`)

- `7752cdf` docs: record timezone decision and correct plan numbering
- `597c7a0` feat(backend): package layout, settings, health route
- `e617d25` docs: README with required sections and State table
- `4c869d8` fix(backend): address review — module app, scoped logger, time guard
- `5f699ac` docs: mark stage 0 done
- `86cd8b2` feat(db): async engine, session dependency, alembic baseline
- `0f788be` feat(db): domain tables, enums and constraints
- `21dd765` fix(db): constrain enum values, case-insensitive email, isolate test DB
- `3a91aa4` feat(auth): register, login, logout with server-side sessions
- `8105f78` feat(auth): shop role and seed shop user
- `004439b` fix(auth): idempotent seed upsert, prod guard, document demo credential
- `11e620e` feat(sales): create/list sales with server time
- `f05f3bd` feat(cart): reserve one unit with 10-minute hold
- `165b753` feat(cart): release hold and view my cart
- `b91d0ee` docs: mark stages 0-3 done in AGENTS.md and README
- `c9e337c` fix(cart): enforce hold expiry, clamp hold to sale end
- `f78b476` feat(paystub): standalone payment stub service
- `d91b529` feat(orders): create order with Idempotency-Key
- `a6b7bf6` test: measure coverage with sysmon over the combined suite
- `d6c7774` feat(payments): pay through paystub, webhook, guarded transitions
- `d640cc0` feat(scheduler): expire holds with a SKIP LOCKED poll loop
- `86e4a38` feat(payments): payment started before hold expiry completes
- `711eba8` fix(payments): correct expired-hold errors, cancel orders on lazy expiry
- `dd16428` feat(outbox): notifications, email stub, sender loop
- `d12a1d1` feat(sales): end-of-sale cleanup
- `db8698d` feat(api): shop stats, payment status check, buyer orders
- `2dae4ad` fix(shop): handle stub errors, cancel orders on post-sale decline
- `0394c80` feat(realtime): SSE endpoint and in-process broadcaster
- `5716f51` test(realtime): two clients see the same stock change
- `9571e31` fix: compose wiring, input validation, SSE buffering, payload consistency
- `d1fe818` fix(review): harden validation, idempotency, webhook and SSE

## Состояние на конец сессии

`make check` зелёный: 69 тестов, покрытие 94.40% (порог 85%), ruff/mypy/frontend
чистые. Таблица «State» в README: строки 1–9 доказаны, T11 (две вкладки) ждёт
frontend-теста. Рабочее дерево чистое, всё запущено в `origin/main`.

## Дальше

Этап 7 (frontend, коммиты 20–25 по плану): router + Pinia + типизированный
api-клиент + экраны auth → витрина → корзина/оплата → кабинет покупателя →
панель магазина → store-тест «два события» (закрывает T11). Затем этап 8:
seed распродажи, финальная таблица State, полный экспорт сессий.
