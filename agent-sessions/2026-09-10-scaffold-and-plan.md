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
- 11:35–11:50 — установлены pre-commit хуки (`make install-hooks`). Первый
  прогон по всем файлам вскрыл: tsconfig — это JSONC (исключён из check-json),
  mypy не был установлен (добавлен в dev-группу со strict), фронтенд-линт
  падал на Node 16 из PATH (добавлен `frontend/.nvmrc` = 24, как в CI).
  После правок все 13 хуков зелёные.

## Коммиты сессии
- `efdaea8` Scaffold flash-sale project: tooling, CI, rules, agent guidance
- `1c9f378` docs: move the spec into docs/acceptance.md
- `ee3a8ac` docs: add the implementation plan
- `d723211` docs: save the first agent session export and log
- `8044d03` build: no default secrets in compose, make env generates .env
- `28c24c8` docs: update the session log and export
- `1ced3ac` build: add pre-commit, rename project to lastunit, add pydantic-settings
- `091ede9` build: make pre-commit pass on all files

## Дальше
План уходит на независимый просмотр другой моделью до начала реализации.
Затем этап 0, коммит 1: пакет `app/`, Settings, `/api/health`, pytest и
остальные dev-зависимости (mypy и pre-commit уже есть). Локально нужен
Node 24: `nvm use` в `frontend/` или `nvm alias default 24`.
