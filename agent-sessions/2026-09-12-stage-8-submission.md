# 2026-09-12 — этап 8: сдача (демо-распродажа в seed + финальные доки)

Инструмент: Claude Code (CLI). Модель: deepseek-v4-pro (не-Anthropic эндпоинт
`api.deepseek.com/anthropic`). Полный экспорт: `2026-09-12-stage-8-submission.jsonl`
(снимок на закрытии сессии).

## Что сделано

- **Коммит 26 — `feat(seed): seed a demo sale …`** — `make seed` (и entrypoint
  контейнера) теперь создаёт демо-распродажу: 5 штук, 99.00, зона
  `Europe/Moscow`, старт через минуту после seed. Идемпотентно по title —
  повторный seed не плодит распродажи. Время берётся из часов Postgres
  (`PostgresClock`), не из локальной машины. Интеграционный тест
  `test_seed_demo_sale_creates_one_sale_starting_soon` добавлен в
  `tests/integration/test_seed.py` рядом с уже существовавшими тестами
  shop-user seed.
- **Смоук с чистого листа** — свежая БД `app_smoke` → `alembic upgrade head` →
  `python -m app.seed` → одна распродажа (`Demo flash sale`, available=5) и один
  пользователь (`shop@example.com` / `shop`); затем БД удалена. Образ бэкенда
  собирается (`docker compose build backend`).
- **Коммит 27 — `docs: final State table, next steps, session exports`** —
  `AGENTS.md` «Status» приведён к финалу (все 9 этапов, а не «0-3»), в README
  «Run locally» упомянута демо-распродажа, «Next steps» переписан под
  завершённый план; добавлен этот экспорт сессии.

## Коммиты сессии (2)

- `26b2489` feat(seed): seed a demo sale so a clean `make up` shows a live flash sale
- docs: final State table, next steps, session exports (добавляет этот файл)

## Проверка

- `make check` зелёный: backend 70 тестов, покрытие 94.51%; frontend 42 теста,
  покрытие 88.82%.
- `make audit` / `make ci` в этой сессии не запускались: активен не-Anthropic
  эндпоинт, а правила проекта запрещают аудит в такой сессии.
