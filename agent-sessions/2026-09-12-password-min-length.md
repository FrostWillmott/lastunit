# 2026-09-12 — минимальная длина пароля и закрытие хвостов аудита

Инструмент: Claude Code (CLI). Модель: deepseek-v4-pro (не-Anthropic эндпоинт
`api.deepseek.com/anthropic`). Полный экспорт —
`2026-09-12-password-min-length.jsonl`.

Сессия 10:59–11:11 UTC. Закрывались последние Low-замечания из
`docs/code-audit-2026-09-12.md`: минимальная длина пароля и поведение
SSE-потока при logout.

## Коммиты

- `8e09f4e` `fix(auth): enforce a minimum password length at registration` —
  `min_length=8` в схеме регистрации. Ограничение стоит только на регистрации:
  логин оставлен без него, чтобы короткий пароль на входе давал 401 (неверные
  данные), а не 422. Длина — контракт создания, а не проверка аутентификации.
- `7d7dc2d` `fix(realtime): close the SSE stream on logout and reopen on login` —
  поток закрывается при выходе, листенеры сохраняются.
- `cb5f231` `fix(register): show the validation message for short passwords` —
  вывод сообщения валидации в `RegisterView` и `minlength="8"` на input.

## Примечание

`openRealtime()` делает ранний возврат при существующем потоке, поэтому
фактически повторно открыть его не может. Сегодня это безвредно (все
контентные маршруты `requiresAuth`, `/login` — `guestOnly`), отмечено при
ревью в `2026-09-12-ci-repair-and-hardening`.
