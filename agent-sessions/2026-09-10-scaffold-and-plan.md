# 2026-09-10 — каркас, точка входа для агентов, план

Инструмент: Claude Code (CLI). Модель: Claude Fable 5.1 (`claude-fable-5-1`).
Полный экспорт: `2026-09-10-scaffold-and-plan.jsonl` (снимок на закрытии
сессии). Email пользователя в экспорте заменён на
`[user email]`.

## Что сделано (по времени)
- 09:18–09:40 — `/init`: заполнен CLAUDE.md по каркасу из шаблона
  workflow-scaffolding. Удалены неприменимые модули правил (clean-architecture,
  pgvector, data-engineering). Папка переименована FastAPIProject → lastunit.
- 09:40–10:00 — схема перевёрнута: `AGENTS.md` — общий вход для всех агентов,
  `CLAUDE.md` = `@AGENTS.md` + Claude-специфика; `.agents/skills` →
  `.claude/skills`. Первый коммит переделан без `.idea/`, история очищена.
  Создана `agent-sessions/`.
- 10:00–11:00 — `/plan`: драфт плана, четыре узла решений вынесены пользователю.
  Решено: логин и пароль; SSE; один процесс; платёжная заглушка как отдельный
  HTTP-сервис. Замечание пользователя про два источника времени (`now()` в SQL
  и `datetime.now()` в Python) → решение «часы Postgres через Clock-протокол и
  параметр `:now`».
- 11:14–11:22 — ТЗ перенесено в `docs/acceptance.md` с нумерацией пунктов,
  план — в `docs/plan.md`. Память агента переведена на новый путь проекта.
- 11:25–11:31 — по замечанию пользователя убраны дефолтные пароли из
  docker-compose: секреты обязательны (`${VAR:?}`), `.env.example` перечисляет
  переменные compose, `make env` генерирует секреты и вызывается из
  `make install` и `make up`. Проверено в копии: compose без `.env` падает с
  именем переменной; `make env` создаёт `.env` с 48-hex паролем, повторный
  вызов ничего не делает, пустой `.env` считается отсутствующим.

## Коммиты сессии
- `efdaea8` Scaffold flash-sale project: tooling, CI, rules, agent guidance
- `1c9f378` docs: move the spec into docs/acceptance.md
- `ee3a8ac` docs: add the implementation plan
- `d723211` docs: save the first agent session export and log
- `8044d03` build: no default secrets in compose, make env generates .env

## Дальше
План уходит на независимый просмотр другой моделью до начала реализации.
Затем этап 0, коммит 1: пакет `app/`, Settings, `/api/health`, dev-зависимости.
