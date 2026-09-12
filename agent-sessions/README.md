# agent-sessions

Exports and logs of the AI agent sessions used to build this project. The spec
asks for prompts or a session export alongside the code and for a visible
timeline, so each session is saved here when it ends, and a final export is
added before submission.

Naming: `YYYY-MM-DD-<short-topic>.<ext>` (jsonl or md). Nothing here is read by
the code or the tooling. Commits a few seconds apart are one working session split
by content (e.g. a docs commit and a feat commit) so the history reads clearly;
the real timeline is the session dates and these exports.

## Что здесь не лежит

Не каждый транскрипт из `~/.claude/projects/` экспортируется:

- **Форки и продолжения** одной работы (одна сессия, возобновлённая после
  обрыва) — экспортируется та, что длиннее и содержит результат.
- **Сессии, где агент вывел `.env` в лог** (11.09). Значения мёртвые,
  локальные и в git не попадали, но публиковать их незачем. Если такой
  транскрипт всё же понадобится, секреты вырезаются перед экспортом, а сам
  факт правки указывается в `.md` — см.
  `2026-09-12-ci-repair-and-hardening.md`.

Правило, предотвращающее саму причину, — в
`.claude/rules/config-hygiene.md` («Never print a secret's value into a log or
transcript»).
