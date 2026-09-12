# Аудит кода (2026-09-12)

Независимый аудит диапазона `efdaea8..HEAD` (56 коммитов, `934fcfe`) второй
моделью: Claude Code (CLI), Claude Fable 5.1. Реализация выполнена
deepseek-v4-pro по `docs/plan.md`. Ничего в репозитории не менялось; единственный
созданный файл — этот отчёт. Эксперименты (сценарии E1–E8 ниже) выполнялись
скриптами вне репозитория против тестовой БД `app_test` и против клона,
поднятого по README.

Шкала: **критично** — приёмочный пункт не выполняется в поставленной сборке;
**высокая** — расхождение README/DECISIONS с реальностью или требование ТЗ без
покрытия; **средняя** — воспроизводимый дефект вне приёмочных пунктов;
**низкая** — робастность, гигиена правил.

## Находки

### 1. [критично] Уведомление «корзина очищена» в поставленном планировщике недостижимо
- `app/scheduler.py:142-143` — `loop` вызывает `run_once` (истечение удержаний)
  **до** `end_ended_sales` с одним и тем же `now`. `app/services/cart.py:129` —
  `expires_at = min(now + 10 min, ends_at)`, то есть у каждого `held` в момент
  `now >= ends_at` уже `expires_at <= now`. `run_once` переводит все такие строки в
  `expired` (без уведомления), и `end_ended_sales` (`app/scheduler.py:84-121`)
  не находит ни одного `held`. Ветка `held → cleared` + `enqueue_cart_cleared`
  в проде — мёртвый код.
- Сценарий: покупатель держит единицу до конца распродажи, не платит. На тике
  `ends_at`: резервация `expired`, заказ `cancelled`, `notifications` — пусто.
  Подтверждено дважды: скриптом (E1: `expired=1 ended=1 cart_cleared_notifications=0`,
  включая удержание за 5 минут до конца) и на реальном compose-стеке (E2E:
  строка `3|4|expired`, таблица `notifications` содержит только два `order_paid`).
- Тест `test_sale_end_clears_holds_and_notifies` (`tests/integration/test_sale_end.py:24`)
  зовёт `end_ended_sales` напрямую, минуя `run_once`, поэтому зелёный.
  Пункт 9 ТЗ («владельцы получают уведомление») в README помечен proven — неверно.
- Минимальная правка: поменять порядок вызовов в `loop` (сначала
  `end_ended_sales`, потом `run_once`) **или** в `run_once` исключить удержания,
  чья распродажа уже закончилась (`JOIN sales ... WHERE sales.ends_at > :now`),
  и добавить тест, который прогоняет ровно последовательность `loop`
  (`run_once` → `end_ended_sales`) при `now = ends_at` и утверждает наличие
  `cart_cleared`.

### 2. [высокая] README не называет модель, которой написан код
- `README.md:10-12` — «the scaffold, plan and audit sessions used Claude Fable 5.1»;
  о deepseek-v4-pro (все этапы 0–8, `agent-sessions/2026-09-11-*.md:3`,
  `2026-09-12-stage-8-submission.md:3`) README молчит, отсылая в каталог.
  ТЗ («Чем делали: какая модель») требует это в описании проекта.
- Правка: одно предложение в README: реализация — deepseek-v4-pro через
  Claude Code на не-Anthropic эндпоинте; аудиты/план — Claude Fable 5.1.

### 3. [высокая] Обещанный экспорт сессии этапа 8 отсутствует
- `agent-sessions/2026-09-12-stage-8-submission.md:4-5` обещает
  `2026-09-12-stage-8-submission.jsonl`; файла нет (в каталоге четыре jsonl,
  последний — `2026-09-11-frontend-stage-7.jsonl`). Коммиты `5672f17`, `80fe49c`,
  `e495e22`, `934fcfe` (все 2026-09-12) экспортом не покрыты. ТЗ просит полный
  экспорт перед сдачей.
- Правка: добавить экспорт или в md явно записать, что экспорта этой сессии нет
  и почему.

### 4. [высокая] INFO-логи приложения под uvicorn не выводятся: почтовая заглушка «ничего не отправляет», LOG_LEVEL мёртв для сервера
- `app/main.py:33` ставит уровень логгеру `app`, но обработчик никто не
  добавляет; uvicorn настраивает только свои логгеры. `app/email_stub.py:10`
  (`logger.info`) и `app/scheduler.py:146` уходят в `lastResort`, который
  печатает только WARNING и выше (`logger.exception` в `scheduler.py:153`
  поэтому виден, а INFO — нет).
  На клон-стеке после двух оплат: `email to` в логе бэкенда — 0 строк,
  `expired ... holds` — 0 строк; единственная строка `app.*` — от seed, который
  сам зовёт `basicConfig` (`app/seed.py:73`).
- Следствие: единственный наблюдаемый след «письма» — `sent_at` в таблице;
  контракт «заглушка пишет в лог» (DECISIONS «Email via an outbox») не
  выполняется; `LOG_LEVEL` меняет поведение только seed'а
  (config-hygiene «Declared means wired»).
- Правка: `logging.basicConfig(level=settings.log_level)` в `create_app` (или
  `log_config` uvicorn'а с обработчиком для `app`), плюс тест, что
  `send_email` даёт запись в `caplog`.

### 5. [средняя] Ключ идемпотентности живёт в `sessionStorage`: во второй вкладке оплатить нельзя
- `frontend/src/stores/cart.ts:24,33,52` — `checkouts` хранятся per-tab. Во
  второй вкладке (или после перезапуска браузера) для той же резервации
  генерируется новый ключ, `POST /orders` упирается в `uq_orders_reservation_id`
  (`app/services/orders.py:89-106`) → 409 «reservation already has an order»,
  `orderId` остаётся `null`, каждое нажатие повторяет 409. Покупатель не может
  ни заплатить, ни «попробовать снова» из этой вкладки — противоречит требованию
  11 ТЗ (две вкладки). Ответ бэкенда на этот запрос уже зафиксирован
  существующим тестом `test_create_order_same_reservation_different_key_409`
  (`tests/integration/test_orders.py:115`); фронтенд-часть цепочки — из кода
  `cart.ts:84-106`, в браузере не воспроизводилась.
- Чужой результат ключ вернуть не может: ключ уникален в паре с `user_id`, а
  повтор с другой резервацией → 409 (`orders.py:58-59`). Проверено.
- Правка: при 409 на создание заказа искать заказ по `reservation_id` в
  `GET /me/orders` и продолжать оплату с ним; либо возвращать `order_id` в
  `GET /me/cart`.

### 6. [средняя] argon2 блокирует event loop на каждом входе/регистрации
- `app/services/auth.py:28,32` — синхронный `pwdlib` внутри `async def`
  (`app/routers/auth.py:41,59`). Замер: hash 51 мс, verify 39 мс (E5). В момент
  старта распродажи волна логинов последовательно останавливает все SSE-потоки
  и `reserve`. python-core [MUST] «no blocking I/O in async paths».
- Правка: `await asyncio.to_thread(verify_password, ...)` /
  `to_thread(hash_password, ...)`.

### 7. [средняя] Три значения по умолчанию для одного секрета вебхука
- `app/config.py:27` (`"dev-secret"`), `paystub/main.py:107` (`"dev-secret"`,
  через `os.environ.get` мимо Settings — config-hygiene [MUST]),
  `tests/integration/test_payments.py:114,227` (`b"dev-secret"` захардкожено).
  Если у разработчика в shell экспортирован `PAYSTUB_WEBHOOK_SECRET`, оба
  webhook-теста падают. `.env.example:20` держит значение пустым и генерирует —
  четвёртая правда.
- Правка: тесты подписывают `Settings().paystub_webhook_secret` (или создают
  приложение с явным `Settings(paystub_webhook_secret=...)`); в paystub — тот же
  pydantic-settings объект или обязательная переменная без дефолта.

### 8. [средняя] `VITE_API_URL` из корневого `.env` никем не читается
- `frontend/vite.config.ts:16` читает `process.env.VITE_API_URL`; Vite грузит
  `.env`-файлы из `frontend/`, а не из корня, и не наполняет `process.env` из
  них. `frontend/Dockerfile` переменную не передаёт. Значение в `.env.example:37`
  и строка README (`README.md:55`) — ручка без эффекта; работает только потому,
  что дефолт совпадает.
- Правка: `loadEnv(mode, path.resolve(__dirname, '..'))` в `vite.config.ts` либо
  убрать переменную из `.env.example`/README и `NON_SETTINGS_KEYS`
  (`tests/unit/test_config_env_contract.py:13`).

### 9. [средняя] Гонка seed по `sales.title` достижима
- `app/seed.py:48-52` — SELECT, затем INSERT без ограничения. DECISIONS
  (`DECISIONS.md:29-31`) объявляет гонку недостижимой «в однопроцессной
  топологии». Два одновременных `seed_demo_sale` дают две живые демо-распродажи
  (E6: `demo sales=2`). Достижимо: `make seed` вручную во время старта
  контейнера (entrypoint тоже сидит) и `docker compose up --scale backend=2`.
- Правка: `pg_advisory_xact_lock(hashtext('demo-seed'))` перед проверкой, либо
  частичный UNIQUE по `title WHERE status='active'`.

### 10. [низкая] Вебхук с не-ASCII подписью — необработанный `TypeError` (500)
- `app/routers/payments.py:93` — `hmac.compare_digest(str, str)` бросает
  `TypeError: comparing strings with non-ASCII characters` (E3, заголовок
  `X-Webhook-Signature: café`). Ответ 500 вместо 401; заглушка в 500 видит
  «недоставлено» и повторяет. Без подписи — 401, корректно. Replay-защиты нет,
  но повтор безвреден: `UPDATE payments ... WHERE status='pending'`
  (`app/services/payments.py:115-126`) — повторная доставка и повторный
  `resolve` дают no-op; проверено (E3, тест `test_order_email_sent_exactly_once`).
- Правка: сравнивать байты: `compare_digest(signature.encode("latin-1", "replace"), expected.encode())`.

### 11. [низкая] Проигравший параллельного двойного клика получает неверное сообщение
- `app/services/payments.py:79-87` — после нулевого `UPDATE` ветка читает
  `reservation.status` из памяти (он ещё `held`), поэтому второй параллельный
  `/pay` получает 409 «reservation is not held» вместо «payment already in
  progress» (E2: `200 pending | 409 reservation is not held`, заглушка вызвана
  один раз, `payments=1`). Фронтенд показывает этот текст покупателю.
- Правка: после нулевого UPDATE перечитать статус `SELECT status ... WHERE id`.

### 12. [низкая] `/api/events` без аутентификации транслирует статусы всех заказов
- `app/routers/events.py:15-24`, `app/services/payments.py:207-209` — любой
  неавторизованный клиент видит `order_status {order_id, status}` по всем
  заказам и `sale_status`. Утечка небольшая (id и статус), но модуль
  transactional-web говорит о «clients of the affected scope».
- Правка: `Depends(current_user)` на `/events` или фильтр по `user_id` в
  полезной нагрузке на стороне SSE-генератора.

### 13. [низкая] Тайминг входа выдаёт существование email
- `app/services/auth.py:98` — при неизвестном email argon2 не вызывается: ~1 мс
  против ~40 мс. Практическая ценность мала: `POST /auth/register`
  (`app/routers/auth.py:43-46`) и так отвечает 409 на занятый email.
- Правка (если нужна): верифицировать фиктивный хэш при `user is None`.

### 14. [низкая] Расхождения имён тестов и утверждений
- `tests/integration/test_payments.py:164` `test_hung_payment_keeps_stock`
  проверяет только `payments.status == pending`; «товар не возвращается и не
  продаётся дважды» реально доказывает
  `test_payment_started_before_expiry_completes_after` (`available == 0`,
  `paying` после `run_once`).
- `test_double_pay_same_key_one_order` и `test_double_pay_calls_paystub_once`
  (`test_orders.py:59`, `test_payments.py:122`) — последовательные запросы, а не
  «двойное нажатие». Параллельный случай доказан только этим аудитом (E2).
  Правка: `asyncio.gather` двух запросов в обоих тестах.
- `tests/integration/test_realtime.py:135-136` — опрос `asyncio.sleep(0.01)`
  с `noqa` и причиной; допустимо, фиксирую как единственное отклонение от
  testing [MUST] «no sleep».

### 15. [низкая] README: устаревшая фраза про Secure-cookie
- `README.md:50` — «(later: Secure cookies)», а `app/routers/auth.py:72` уже
  ставит `secure=app_env != "dev"`. Проверено на клоне: в dev cookie
  `HttpOnly; SameSite=lax` без `Secure`.

### 16. [низкая, процесс] Записи DECISIONS отстают от коммитов с решением
- AGENTS.md требует запись «in the same change as the decision». Clamp удержания
  к `ends_at` принят в `c9e337c` (11.09 13:13), outbox и обнуление остатка —
  в `dd16428`/`d12a1d1` (14:11/14:14); обе записи DECISIONS появились только в
  `9571e31` (15:05, «fix: compose wiring…»). Отмена заказа при отклонении после
  конца распродажи (`2dae4ad`) записи не получила вовсе (см. список DECISIONS
  ниже). Ревьюер, проверяющий постепенность по датам записей, увидит расхождение.

### Проверено, дефекта не найдено (шаги 3–4, для протокола)
- Broadcast только после `commit` во всех пяти местах: `cart.py:139-144`,
  `cart.py:190-191`, `scheduler.py:58-60`, `scheduler.py:122-126`,
  `payments.py:206-208`. Outbox-строка пишется в той же транзакции, что и
  переход (`payments.py:164-166` до `commit` в 206; `scheduler.py:119-122`).
- Вебхук раньше commit `/pay` невозможен по построению: `provider_ref`
  генерирует бэкенд и коммитит (`payments.py:89-99`) до HTTP-вызова
  (`routers/payments.py:66`); заглушка узнаёт ссылку только из этого вызова.
- Двойное «оплатить» до commit первого: `UPDATE reservations ... WHERE
  status='held'` сериализуется блокировкой строки; проигравший получает 0 строк
  (E2). Partial UNIQUE `uq_payments_order_pending` — второй рубеж, до него дело
  не доходит.
- Оплата на границе `expires_at` параллельно с тиком: `start_payment`
  (`expires_at > :now`) и `run_once` (`FOR UPDATE SKIP LOCKED`, `expires_at <= :now`)
  борются за одну строку; тик, не получивший блокировку, пропускает строку и на
  следующем тике видит `paying`. Запрос, чья транзакция началась до истечения,
  может выиграть у тика, начавшегося после, — приемлемо.
- Окончание распродажи при `paying`: `available = 0`, резервация остаётся;
  `approved` позже → `sold`/`paid`/письмо (E7), `declined` позже → `cleared`,
  заказ `cancelled`, `cart_cleared`, единица не возвращается (E8, документировано
  в плане). `available` при этом теряет единицу навсегда — осознанно.
- `PostgresClock.now(db)` = `transaction_timestamp()` (E4: два чтения через 0,5 с
  дают одно значение; после `commit` — свежее). В `/pay` второе
  `clock.now(db)` идёт после commit, значит свежее; в планировщике `now` тика
  переиспользуется тремя функциями после промежуточных commit — согласованно
  и безвредно. Единственный риск — будущий код, который после `commit`
  продолжит использовать старый `now`; проверять на ревью.
- Письмо дважды: `send_pending` (`notifications.py:57-64`) шлёт, потом
  коммитит `sent_at`; падение между ними даёт повтор (at-most-one duplicate,
  допущено модулем). Второй строки outbox не будет — UNIQUE `(kind, entity_id)`.
- Cookie: HttpOnly, SameSite=Lax, Secure вне dev, срок = `SESSION_TTL_DAYS`;
  все мутации — POST/DELETE с JSON, Lax не отдаёт cookie на cross-site POST.
  Логи: токены, пароли, номера карт в логи не попадают (номер карты только в
  теле POST к заглушке; заглушка не логирует). Секреты: `.env` не в git,
  сгенерированные значения в `agent-sessions/` не найдены (grep по текущим
  значениям и по шаблону `=[0-9a-f]{40,}`), `.env.example` секретов не содержит,
  compose требует переменные через `${VAR:?}`.
- Шаг 5, механика: `datetime.now/utcnow/func.now/time.time/date.today` в
  `app/` — 0 (тест `test_no_local_time` есть); `os.environ` вне Settings — только
  `paystub/main.py:107` (п. 7) и conftest; `time.sleep` в тестах — 0;
  `except Exception` — только `app/scheduler.py:152` с логированием
  (оправдано, но это [MUST]-исключение без документированного escape в модуле);
  `relationship`/lazy-load — не используется, все связи через явные SELECT;
  бизнес-логики в роутерах нет; `fetch` только в `src/api/client.ts`;
  `skip/xfail` — 0; каждое поле Settings имеет потребителя (кроме п. 4 —
  `log_level` для сервера); `.env.example` ↔ Settings проверяется тестом.
  Все компоненты — `<script setup lang="ts">`, `v-for` с id-ключами, состояние
  в Pinia.

## Таблица State (версия аудита)

| # | Пункт | Тест | Реальная база / коммиты / соединения | Время | Оценка | Почему отличается от README |
|---|---|---|---|---|---|---|
| 1 | До старта нельзя; в момент старта открывается у всех | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed` | да, реальные commit, один клиент | `FrozenClock` ровно на границе | **partially proven** | Совпадает. Недоказано: (а) одновременность на сервере — тест с двумя соединениями при `now == starts_at` (оба 201) и при `starts_at − 1 мкс` (оба 409) закрыл бы это; (б) на клиенте старт определяется собственным тикающим таймером от `server_now` со смещением, включающим половину RTT, а сервер не шлёт события «началось». Полностью доказуемо только после добавления `sale_status: started` из планировщика и store-теста на него. |
| 2 | Остатки меняются у всех без обновления | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server` | да; два подписчика брокастера + один настоящий uvicorn/SSE-клиент | frozen | proven | Два подписчика — на уровне брокастера, не два HTTP-клиента; E2E на клоне: 7 событий получены внешним `curl`. |
| 3 | Последняя единица — одному из двух | `test_last_unit_two_buyers_one_wins` | да; два `SessionFactory()`, `gather`, реальные commit | frozen | proven | — |
| 4 | Удержание 10 мин, возврат, все видят | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | да; `run_once` напрямую | frozen | proven | `loop` не прогоняется ни одним тестом (см. п. 1). |
| 5 | Оплата до истечения завершается после | `test_payment_started_before_expiry_completes_after` | да; отдельные сессии на шаг | frozen | proven | — |
| 6 | Зависла: заказ pending, не продаётся дважды, досчитывается | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | да | frozen | proven | «keeps_stock» остаток не проверяет; остаток доказывает тест из строки 5. Подтверждено E2E (`…9995` → resolve → paid). |
| 7 | Двойное «оплатить» — один заказ, одно списание | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | да, но запросы последовательные | frozen | proven (параллельность — только аудитом) | E2: `gather` двух `POST /orders` → один заказ; двух `POST /pay` → одна попытка, заглушка вызвана один раз. Тесты стоит сделать параллельными. |
| 8 | Одно письмо о заказе | `test_order_email_sent_exactly_once` | да; повтор вебхука → та же одна строка | frozen | proven (на уровне outbox) | «Ровно одно» верно для outbox; отправка — at-most-one duplicate при падении между send и commit; в проде отправка в лог не видна (п. 4). |
| 9 | Конец: непроданное снято, корзины очищены, владельцы уведомлены | `test_sale_end_clears_holds_and_notifies` | да, но `end_ended_sales` вызван в обход `run_once` | frozen | **not proven** (уведомление не выполняется) | Снятие (`available = 0`) и очистка корзин работают; уведомление владельцу в поставленном `loop` недостижимо — п. 1, подтверждено на клоне. |
| T11 | Две вкладки в синхроне | строка 2 + `useRealtime.test.ts` + `sales.test.ts` «two successive stock events» | да / jsdom | — | proven, с оговоркой | Витрина и кабинет — да. Оплата из второй вкладки той же резервации — 409 навсегда (п. 5). |

## Записи DECISIONS, расходящиеся с кодом

1. **2026-09-11 «Email via an outbox; sale end zeroes stock»** (`DECISIONS.md:52-57`):
   «clears its held reservations» — в проде удержания уходят в `expired` через
   `run_once`, а не в `cleared`, и без уведомления (п. 1). «the scheduler sends
   them through the email stub» — отправка в лог не наблюдаема (п. 4).
2. **2026-09-10 «Declined payment keeps the reservation and the order»**
   (`DECISIONS.md:119-122`): после `ends_at` код переводит резервацию в `cleared`
   и **отменяет заказ** с уведомлением (`app/services/payments.py:185-203`,
   коммит `2dae4ad`). План (`docs/plan.md:217-218`) обещал «заказ не меняется».
   Записи, которая бы это superseded, нет: `2dae4ad` DECISIONS не трогал.
3. **2026-09-11 «Sale times are absolute, in the shop's IANA zone»**
   (`DECISIONS.md:80-85`): «renders the times back in that zone» — API отдаёт
   `starts_at`/`ends_at` в UTC (`...Z`) плюс отдельное поле `timezone`
   (`app/routers/sales.py:75-77`; E2E: `"starts_at":"2026-09-12T05:49:24Z","timezone":"UTC"`).
4. **2026-09-12 «Demo sale is seeded, keyed by title…»** (`DECISIONS.md:23-33`):
   «the check-then-act race is unreachable» — достижима (п. 9, E6).
5. **2026-09-12 «Clock reads now() through the request's own session»**:
   реализовано как записано; семантика «transaction start time» подтверждена (E4).
6. **2026-09-10 «No default secrets in compose»**: для compose верно; но
   `Settings.paystub_webhook_secret = "dev-secret"` и такой же дефолт в paystub
   означают, что вне compose бэкенд и заглушка стартуют с известным секретом
   (п. 7). Запись про демо-пароль магазина это оговаривает, про секрет
   вебхука — нет.

Остальные записи (SSE вместо WebSocket и его пересмотр на native `EventSource`;
один процесс; paystub как HTTP-сервис с вебхуком; сессии без SECRET_KEY;
argon2id; один активный hold на покупателя; попытки оплаты с одним pending;
guard по времени в переходе; «зависла» = pending и таймаут; без сверки;
один источник времени; fire-late; порог покрытия фронтенда; AGENTS.md;
модули правил; clamp удержания к `ends_at`; демо-аккаунт магазина) — совпадают
с кодом.

## README «Next steps» против того, что аудит признал недоказанным

`README.md:96-105` перечисляет LISTEN/NOTIFY и worker, автотаймаут зависших
платежей со сверкой, пагинацию. Не упомянуто:

- Дефекты, а не «следующий заход» (в Next steps им не место, их надо чинить):
  уведомление при конце распродажи (п. 1); оплата из второй вкладки (п. 5);
  невидимые INFO-логи и почтовая заглушка (п. 4).
- Осознанные ограничения, которые честнее записать в State/Next steps:
  единица, безвозвратно теряемая при отклонении после `ends_at` (`available`
  уже 0); отсутствие серверного события «распродажа началась» — единственный
  путь сделать строку 1 полностью доказуемой; `/api/events` без авторизации
  (п. 12); блокирующий argon2 (п. 6).

## Вердикт: **fix-first**

Блокируют: п. 1 (приёмочный пункт 9 не выполняется, а README говорит proven),
п. 2 и п. 3 (обязательные deliverables ТЗ: модель в README, экспорт последней
сессии), п. 4 (заявленный контракт почтовой заглушки не наблюдаем). После них —
п. 5 (две вкладки при оплате) и п. 6.

## Шаг 1: что запускалось и с каким результатом

Машина аудита: macOS, Docker Desktop, uv 0.12.x, Node 24.2.0 через nvm.

| Команда | Результат |
|---|---|
| `docker compose up -d db` | `lastunit-db-1` уже был поднят и healthy. |
| `make check` (первый прогон, в shell Node **16.20.2**) | **FAIL** на `frontend-check`: `eslint . → TypeError: configs.findLastIndex is not a function` (`@vue/eslint-config-typescript`). Причина — окружение: `frontend/.nvmrc` = 24, README Prerequisites требует Node 24. Не дефект репозитория. Бэкенд-часть прошла: 75 passed, coverage 94.66 % (порог 85). |
| `make check` (Node 24.2.0) | **PASS**. Backend: ruff, format, mypy, 75 passed, 3 DeprecationWarning (starlette/httpx, не проекта), coverage 94.66 %. Frontend: lint, prettier, vue-tsc, 45 passed (7 файлов), coverage lines 95.62 % / statements 87.38 % (порог 80). |
| `make test-integration` | **PASS**: 59 passed, 11.4 с. |
| `make ci` | **PASS**: check + `frontend-build` + `uv audit` (0 уязвимостей в 36 пакетах) + `npm audit` (0). |
| `make docker-build` | **PASS**: три образа собраны. |
| `git clone <repo> <scratch>/clone` → `make install` | **PASS**, 4,2 с (`make env` создал `.env` с сгенерированными секретами; `uv sync`; `npm ci`). |
| `make up` в клоне | **PASS**, 10,8 с, четыре контейнера. Отклонение от буквального README: на этой машине порты 5432/8000/8080 заняты посторонними контейнерами, поэтому в клон добавлен `docker-compose.override.yml`, меняющий **только host-порты** (15432/18000/18001/18080); внутренняя схема (`backend:8000`, `paystub:8001`, `db:5432`, nginx-proxy) не тронута. |
| `curl /api/health` (через backend) | `200 {"status":"ok"}` — после ~6 с (миграции + seed в entrypoint). |
| `curl /api/sales` (через backend и через nginx :80) | `200`, одна демо-распродажа `Demo flash sale`, 5 шт., `phase: upcoming`, старт через минуту после seed. |
| `curl /` (nginx) | `200`, SPA. |
| `curl -N /api/events` (через backend и через nginx, 3 с) | `200 text/event-stream`, chunked, `X-Accel-Buffering: no`; за 3 с тела нет (ping раз в 15 с) — соединение держится. |
| `curl :8001/docs` (paystub) | `200`. |
| `POST /api/auth/login` (`shop@example.com`/`shop-password`) | `200`, `Set-Cookie: session=…; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax` (без `Secure` — dev). |
| E2E на клоне (сценарий скриптом): распродажа на 90 с, 3 шт.; b1 reserve→order→pay `…0000`; b2 pay `…9995` → `check` (pending) → `resolve` на заглушке; b3 reserve без оплаты; ожидание конца | b1: `approved` синхронно, вебхук от заглушки принят (`POST /api/payments/webhook 200`), заказ `paid`. b2: `pending`, `check` → `pending`, `resolve approved` → заказ `paid`. Stats до конца: `available 0, sold 2, in_cart 1`. После конца: `phase ended`, `available 0`, `in_cart 0`; резервации `sold, sold, expired`; notifications: два `order_paid` (`sent = t`), **`cart_cleared` — нет**; SSE у внешнего клиента: 4 `stock_changed`, 2 `order_status`, 1 `sale_status ended`. |
| `docker compose down -v` в клоне | выполнено, стек и volume удалены. |
| Эксперименты E1–E8 (скрипт вне репо, БД `app_test`) | E1 порядок тика → `notifications=0` (п. 1). E2 параллельные `/orders` и `/pay` → 1 заказ, 1 попытка, 1 вызов заглушки (п. 11). E3 вебхук: без подписи 401; не-ASCII подпись → `TypeError` (п. 10). E4 `now()` = начало транзакции. E5 argon2 51/39 мс (п. 6). E6 два seed → 2 распродажи (п. 9). E7 approve после конца → `sold/paid`, письмо. E8 pay после `ends_at` до тика → `HoldExpiredError`; decline после конца → `cleared/cancelled`, единица не возвращена. |

## Вопросы человеку

1. Пункт 9: при исправлении п. 1 — должны ли удержания, истёкшие ровно в момент
   конца распродажи, считаться «очищенными по окончании» (письмо) или «истёкшими»
   (без письма)? Сейчас `expires_at` clamp'ится к `ends_at`, и эти два события
   неразличимы; от ответа зависит, менять порядок в `loop` или условие в `run_once`.
2. Отклонение после `ends_at` отменяет заказ (`2dae4ad`) вопреки плану и
   DECISIONS 2026-09-10. Это осознанное решение, требующее superseding-записи, или
   откат к «заказ не меняется»?
3. `DECISIONS` «renders the times back in that zone» — нужна ли отдача времени в
   зоне магазина в API (и тогда правка кода), или исправить запись?
4. Публичный `/api/events` со статусами всех заказов — приемлемо для демо или
   закрыть авторизацией?
5. Единица, потерянная при отклонении после конца распродажи (`available` уже 0),
   — фиксируется как принятое поведение в README «State»/«Next steps»?
6. Экспорт сессии этапа 8 (`2026-09-12-stage-8-submission.jsonl`): будет добавлен
   или в md записать, что его нет?
7. История коммитов: пары с разницей 0–3 с (`7752cdf`/`597c7a0`/`e617d25`,
   `d91b529`/`a6b7bf6`, `4c869d8`/`5f699ac`, `28c24c8`/`8044d03`) — созданы одним
   заходом; ревьюер, проверяющий «ход работы во времени», это увидит. Оставить или
   пояснить в `agent-sessions/`?
8. Секрет вебхука со значением по умолчанию `dev-secret` в двух местах — оставить
   как демо-удобство (тогда записать в DECISIONS рядом с демо-паролем) или убрать
   дефолт?

## Security review

Отдельный прогон `/security-review` (Claude Code, Claude Fable 5.1) по тому же
диапазону `efdaea8..HEAD`, уже после fix-first-коммитов (`ab0eaa3`). Метод:
три параллельных поиска по зонам (auth/API-роутеры; платежи, вебхук, paystub,
планировщик, инфраструктура; фронтенд и SSE), затем отдельный фильтр ложных
срабатываний на каждого кандидата с порогом 8/10. Тесты, `*.md` и
`agent-sessions/` вне области; DoS, rate limiting и хранение секретов на диске
исключены правилами скилла.

**Результат: ни одного HIGH или MEDIUM-нахождения.** Шесть кандидатов уровня
Low, каждый отброшен фильтром с оценкой 2/10.

| Кандидат | Место | Почему отброшен |
|---|---|---|
| Paystub опубликован на хосте; `POST /payments` с произвольным `callback_url` и `/resolve` без аутентификации | `docker-compose.yml:46-47`, `paystub/main.py:125-156` | Заглушка по дизайну (README, DECISIONS). Подделка вебхука требует pending `provider_ref` (128 бит, отдаётся только роли shop); результат совпадает с вводом карты `…0000`. |
| SSE-поток не закрывается при logout; `user_id` фиксируется при подключении | `app/routers/events.py:27-32`, `frontend/src/composables/useRealtime.ts` | Payload — только `order_id` и `status`; сторы его не рендерят, а перезапрашивают с текущей cookie. Сценарий требует общий браузер и смену пользователя в одной вкладке без перезагрузки. |
| `APP_ENV` по умолчанию `dev`: cookie без `Secure`, `/docs` открыт | `app/config.py:17`, `app/routers/auth.py:72` | Env-переменная — доверенное значение; в стеке нет TLS-терминации; переключатель задокументирован в README и `.env.example`. |
| Register возвращает 409 для занятого email | `app/routers/auth.py:40-45` | Стандартное поведение регистрации; email-верификация невозможна с почтовой заглушкой; утечка — один бит. |
| Пароль без `min_length` | `app/routers/auth.py:19-26` | Пробел в hardening; стороннего пути атаки нет без brute force (исключён правилами). |
| httpx логирует URL с `provider_ref` при `check` | `app/main.py:37`, `app/paystub_client.py:49` | Логирование URL считается безопасным; ref уже виден роли shop через `/shop/sales/{id}/stats`. |

### Проверено, дефекта не найдено
- **Сессии.** `secrets.token_urlsafe(32)`, SHA-256 хеш в БД с UNIQUE, проверка
  `expires_at` по часам БД, новый токен на каждый login, logout удаляет строку.
  Cookie `httponly` + `samesite=lax`; CORS-middleware нет, значит cross-site
  POST/DELETE не несут cookie.
- **Авторизация.** Каждый мутирующий и приватный маршрут идёт через
  `current_user` или `require_shop`; `register` жёстко назначает роль BUYER.
  Все id-параметры (reservation, order) скоупятся по `user_id` в сервисном
  запросе; ключ идемпотентности защищён `UNIQUE(user_id, idempotency_key)`.
  `/api/events` резолвит cookie тем же `user_for_token`, `order_status`
  доставляется только владельцу. Побочный эффект этого скоупа — функциональный,
  не security: витрина магазина подписывалась на `order_status` и после скоупа
  перестала видеть оплаты (события склада тут нет — `available` уменьшается ещё
  на этапе брони). Исправлено отдельным событием `sale_stats` без скоупа, см.
  DECISIONS и `test_payment_result_broadcasts_sale_stats_to_everyone`.
- **Платежи.** Вебхук: HMAC-SHA256 по сырому телу, `compare_digest` на bytes.
  Replay — no-op через guarded `UPDATE … WHERE status='pending'` и partial
  unique index на `(order_id) WHERE status='pending'`. `amount_minor` берётся из
  `sale.price_minor`, не от клиента. Номер карты не хранится и не логируется.
  `callback_url` и URL заглушки — только из `Settings`.
- **Инъекции.** `text()` только с литералами (`SELECT now()`, advisory lock);
  `ZoneInfo` отбрасывает `..` и абсолютные пути; email нормализуется и
  ограничен CHECK/UNIQUE. Во фронтенде нет `v-html`/`innerHTML`; единственный
  `:href` — константа с `rel="noopener"`; redirect после login обрабатывается
  vue-router как same-origin путь.
- **Секреты и сборка.** compose использует `${VAR:?}`, `.env.example` без
  значений, `.env` не коммитился, `.dockerignore` исключает `.env*`,
  `loadEnv` с дефолтным префиксом `VITE_`, `sourcemap: false`, CI с
  `permissions: contents: read` и SHA-пинами, `npm ci --ignore-scripts`.
- **Seed и prod-guard.** `seed_demo_sale` и демо-пользователь не создаются при
  `APP_ENV=prod`; `/docs` и `/openapi.json` в prod отключены.

## Последующий ревью (`/code-review`, Claude Opus 5)

Прогон по тем же fix-first-коммитам нашёл два дефекта, внесённых самими
исправлениями; оба закрыты в этом же проходе.

| Дефект | Место | Исправление |
|---|---|---|
| Скоуп `order_status` по покупателю отрезал витрину магазина от живых обновлений sold/revenue/pending | `app/services/payments.py`, `frontend/src/stores/shop.ts` | Дополнительное событие `sale_stats` без скоупа; витрина подписана на него вместо `order_status`. Тест: `test_payment_result_broadcasts_sale_stats_to_everyone` |
| Повторное чтение брони в `start_payment` было no-op: identity map сессии уже держал устаревший объект, проигравший гонку получал «reservation is not held» | `app/services/payments.py` | `.execution_options(populate_existing=True)` на перечитывающем `select`. Тест: `test_start_payment_with_stale_hold_in_session_reports_pending_payment` (детерминированный, без опоры на планировщик корутин) |

Оба теста проверены «красными» до исправления.
