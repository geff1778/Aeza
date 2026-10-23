# Отчёт о тестировании Invoice Keeper

Все результаты ниже получены реальным запуском. Для каждой проверки указана
команда и фактический результат. Проверки, которые не удалось выполнить,
перечислены отдельно с причиной.

Дата прогона: 2026-10-23. Среда: Linux, Docker Compose, PostgreSQL 16.

---

## 1. Сводка

| Проверка | Результат | Доказательство |
|---|---|---|
| Backend unit + API-тесты | **106 passed, 0 failed** | `cd backend && pytest -q` |
| Сборка frontend | **успешно** | `cd frontend && npm run build` |
| Type checking | **успешно, 0 ошибок** | `cd frontend && npm run typecheck` |
| Линтер frontend | **успешно, 0 ошибок и предупреждений** | `cd frontend && npm run lint` |
| E2E (Playwright, desktop + mobile) | **42 passed, 0 failed** | `cd frontend && npx playwright test` |
| Проверка запущенного стека | **57 passed, 0 failed** | `python scripts/verify_stack.py` |
| Миграции | **применяются, повторный запуск безопасен** | `alembic upgrade head` дважды |
| Docker Compose | **4 сервиса healthy** | `docker compose up --build -d`, `docker compose ps` |
| Persistence после перезапуска | **данные сохранены, дублей нет** | счётчики до/после `docker compose restart` |
| Telegram (реальная доставка) | **не проверена — нет токена** | см. раздел 7 |
| Email (реальная доставка) | **не проверена — нет SMTP** | см. раздел 8 |

---

## 2. Backend: 106 тестов

```
$ cd backend && .venv/bin/python -m pytest -q
........................................................................ [ 74%]
.........................                                                [100%]
106 passed in 21.18s
```

Распределение по файлам:

| Файл | Тестов | Что проверяет |
|---|---|---|
| `tests/test_api.py` | 54 | аутентификация, RBAC, CRUD, статусы, аудит, бюджеты, чеки, OpenAPI |
| `tests/test_notifications.py` | 20 | правила напоминаний, outbox, идемпотентность, повторные попытки, callback |
| `tests/test_dates.py` | 13 | календарная арифметика, конец месяца, високосный год, горизонт |
| `tests/test_payments_service.py` | 11 | генерация периодов, независимость, завершение, аудит |
| `tests/test_status.py` | 8 | формула статуса, окно «скоро срок», оплата с просрочкой |

Ключевые покрытые сценарии (выборка из `pytest --collect-only`):

- `test_unpaid_statuses[pending|due_soon|overdue]` — три состояния неоплаченного
  платежа, включая «в день срока ещё не просрочен».
- `test_overdue_formula_is_strictly_greater_than_due_date` — просрочка строго
  `today > due_date`.
- `test_late_payment_is_not_reported_as_overdue` — оплаченный с опозданием
  период не считается неоплаченным.
- `test_month_end_sequence_does_not_drift` — 31 января → 28/29 февраля → 31 марта
  без «залипания» на 28.
- `test_leap_year_february_29_anchor` — високосный год.
- `test_periods_are_independent` — оплата одного периода не влияет на другие.
- `test_overdue_period_does_not_block_future_generation` — просрочка не
  блокирует генерацию.
- `test_deactivate_stops_generation_and_keeps_history` — завершение сохраняет
  историю.
- `test_worker_rerun_does_not_duplicate` — три прогона worker, одна запись.
- `test_no_configured_channel_enqueues_nothing_even_when_overdue` — без канала
  outbox остаётся пустым (нет фиктивной доставки).
- `test_callback_marks_paid_and_is_idempotent` — повторное нажатие не создаёт
  новую запись.
- `test_bootstrap_admin_is_protected` — bootstrap-администратора нельзя удалить
  или понизить.
- `test_regular_user_cannot_*` — обычный пользователь не может создавать
  платежи, управлять пользователями, читать аудит, менять бюджет.
- `test_currencies_are_not_summed_together` — валюты не суммируются.
- `test_internal_errors_do_not_leak_details` — ошибки не раскрывают внутренности.
- `test_attachment_rejects_bad_type` / `test_attachment_rejects_oversize` —
  ограничения загрузки файлов.
- `test_occurrences_reject_unknown_sort_column` — имя колонки сортировки
  валидируется (защита от инъекции в ORDER BY).
- `test_config_validation_*` — слабый `SECRET_KEY`, пустой `ADMIN_PASSWORD`,
  production-требования (`COOKIE_SECURE`, placeholder-секрет) и валидные
  настройки; сообщения об ошибках не содержат значений.
- `test_app_refuses_to_start_with_bad_config` — `create_app()` падает с
  `RuntimeError`, не выдавая значение секрета.

---

## 3. Frontend: сборка, типы, линтер

```
$ cd frontend && npm run build
✓ built in ...                     # успешно

$ npm run typecheck
                                   # 0 ошибок (tsc --noEmit)

$ npm run lint
> eslint . --max-warnings=0
                                   # 0 ошибок, 0 предупреждений
```

Конфигурация линтера (`eslint.config.js`) включает рекомендованные наборы
`typescript-eslint` и `eslint-plugin-react-hooks`. Отключены две проверки, и
причины зафиксированы в самом файле:

- `react-hooks/set-state-in-effect` — срабатывает на штатном для проекта паттерне
  загрузки данных (`useEffect` + fetch) при отсутствии клиентского кэша;
- `react-refresh/only-export-components` — подсказка только для HMR.

Проверки `rules-of-hooks` и `exhaustive-deps` остаются включёнными.

---

## 4. E2E: 42 теста (Playwright)

```
$ cd frontend && npx playwright test
Running 42 tests using 1 worker
...
42 passed (51.9s)
```

Два проекта: `chromium-desktop` (1440×900) и `chromium-mobile` (390×844) —
по 21 сценарию в каждом.

Основной сквозной сценарий (`payment lifecycle across two users`):

1. администратор создаёт регулярный платёж → появляется первый период;
2. обычный пользователь видит **тот же** общий период;
3. пользователь отмечает оплату → статус изменился;
4. статус сохраняется после перезагрузки страницы;
5. исправление фактической даты переводит «оплачено с просрочкой» в «оплачено
   вовремя»;
6. снятие отметки возвращает просрочку;
7. периоды независимы, история сохраняется после завершения платежа.

Плюс проверки: редирект без авторизации, отсутствие админ-навигации у обычного
пользователя, недоступность страницы пользователей напрямую, ошибка при неверном
пароле, реальная инвалидация сессии при выходе, Dashboard и календарь на реальных
данных, страницы пользователей/аудита/бюджетов, пустой результат поиска, фильтр
по статусу, отсутствие горизонтального переполнения на мобильном, работа
мобильной навигации через «гамбургер», отсутствие ошибок в консоли браузера.

---

## 5. Проверка запущенного стека: 57 проверок

```
$ python scripts/verify_stack.py
...
PASSED: 57   FAILED: 0
All stack checks passed.
```

Скрипт работает по реальному HTTP через reverse proxy: вход обеими ролями,
разграничение прав, общий статус для двух пользователей, расчёт просрочки,
исправление даты, снятие отметки, независимость периодов, сохранение истории
после завершения, бюджеты, аудит, инвалидация сессии.

### Независимая проверка RBAC (curl, обычный пользователь)

```
POST   /recurring-payments   -> 403
DELETE /recurring-payments/1 -> 403
POST   /users                -> 403
DELETE /users/1              -> 403
PATCH  /users/1              -> 403
GET    /audit                -> 403
GET    /payment-occurrences  -> 200   (общие платежи доступны)
GET    /payment-occurrences  (без cookie) -> 401
PATCH  /payment-occurrences/1 (без CSRF-токена) -> 403
```

### Защита bootstrap-администратора

```
DELETE /users/1        -> 403  {"detail":"Bootstrap-администратора нельзя удалить"}
PATCH  /users/1 role=user -> 403  {"detail":"Bootstrap-администратора нельзя понизить в правах"}
```

---

## 6. Миграции и persistence

### Миграции

```
$ docker compose exec api alembic upgrade head   # запуск 1
$ docker compose exec api alembic upgrade head   # запуск 2 — безопасен
$ docker compose exec api alembic current
f21c456f67da (head)
```

### Сохранение данных при перезапуске

```
=== до перезапуска ===
occurrences=235 audit=227 paid=17 payments=17

$ docker compose restart

=== после перезапуска ===
occurrences=235 audit=227 paid=17 payments=17
```

Счётчики совпадают — данные пережили перезапуск.

### Отсутствие дублей после рестарта worker

```
dup_periods=0
dup_notifications=0
```

---

## 7. Telegram

### Что проверено (автоматические тесты)

- Формирование текста: название, сумма, валюта, срок, число дней
  (`test_message_contains_title_amount_due_and_days`).
- Напоминание за три дня (`test_reminder_is_enqueued_three_days_before`).
- Немедленное напоминание при близком сроке
  (`test_immediate_reminder_for_close_due_date`).
- Отсутствие напоминания по оплаченному периоду
  (`test_no_reminder_for_paid_period`).
- Отсутствие напоминания после завершения платежа
  (`test_no_reminder_after_payment_completed`).
- Идемпотентность при повторном запуске worker
  (`test_worker_rerun_does_not_duplicate`).
- Повторная попытка после ошибки и остановка после лимита
  (`test_failure_is_recorded_and_retried`, `test_max_attempts_stops_retrying`).
- Идемпотентность callback-кнопки «Оплачено»
  (`test_callback_marks_paid_and_is_idempotent`).
- Отклонение некорректного callback и завершённого платежа
  (`test_callback_rejects_bad_payload`, `test_callback_rejects_completed_payment`).
- Ограничение по `TELEGRAM_ALLOWED_USER_IDS` (`test_allowed_user_restriction`).
- Без токена успех не имитируется (`test_no_token_means_no_simulated_success`).

Все перечисленные проверки используют **mock-транспорт** (`FakeTelegram`).

### Что не проверено

**Реальная доставка в Telegram не подтверждена**: действующий
`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в среде отсутствуют. Mock-тест не
является доказательством реальной доставки. Инструкция по подключению — в
README, раздел «Получение Telegram-токена».

При отсутствии токена worker пишет в лог предупреждение и **не отправляет и не
имитирует** уведомления; outbox остаётся пустым. Это подтверждено тестом
`test_no_configured_channel_enqueues_nothing_even_when_overdue`.

---

## 8. Email (SMTP)

### Что проверено

- Ошибка доставки корректно фиксируется без настроенного SMTP
  (`test_email_transport_records_failure_without_smtp`).
- Отправка через внедрённый тестовый транспорт
  (`test_email_uses_injected_transport`).

### Что не проверено

**Реальная доставка письма не подтверждена**: SMTP-реквизиты отсутствуют.
Проверен только тестовый транспорт. При пустом `SMTP_HOST` канал отключён, а в
интерфейсе отображается статус «Не настроено».

---

## 9. Визуальная и доступностная проверка

Проведена автоматизированная инспекция вычисленных стилей на страницах Dashboard,
Payments, Calendar, Budgets и на мобильном разрешении.

Найдено и исправлено:

| Проблема | Было | Стало |
|---|---|---|
| Контраст второстепенного текста | `#98a2b3` — 2.58:1 на белом | `#667085` — 4.97:1 (WCAG AA) |
| Контраст вторичного текста | `#667085` | `#475467` — 7.69:1 |
| Размер метаданных | 11px в 13 местах | 12px |
| Высота компактных кнопок | 27px | ≥32px |
| Кликабельная область ссылок в таблице | 16px | 32px |
| Кнопка меню на мобильном | 30×24 | 40×40 |

Результат повторной инспекции:

```
DESKTOP payments: smallText=0  (текст мельче 12px отсутствует)
MOBILE  payments: smallText=0
MOBILE  horizontal overflow: 0 px
```

Статусы различаются и цветом, и текстом. Учтено `prefers-reduced-motion`
(в `tokens.css` анимации отключаются системной настройкой).

---

## 10. Проверка отсутствия секретов

```
$ git check-ignore -v .env
.gitignore:12:.env      .env            # .env игнорируется
```

Сканирование отслеживаемых файлов на реальные секреты (токены ботов, ключи,
пароли): **не найдено**. В репозитории присутствуют только демонстрационные
пароли синтетических учётных данных, помеченные как таковые и переопределяемые
переменными окружения (`DEMO_PASSWORD`, `ADMIN_PASSWORD`, `VERIFY_*`,
`E2E_*`).

`frontend/test-results/` (артефакты Playwright, включая трассировки с
демонстрационными паролями) добавлен в `.gitignore` и в репозиторий не попадает.

---

## 11. Что осталось непроверенным или заблокировано

| Пункт | Причина | Влияние |
|---|---|---|
| Реальная доставка в Telegram | нет действующего токена | логика проверена mock-транспортом; внешняя доставка непроверена |
| Реальная доставка email | нет SMTP-реквизитов | то же |
| Проверка на реальном HTTPS-домене | локальная среда | cookie `Secure` включается через `COOKIE_SECURE=true` в production |

Все три пункта требуют внешних реквизитов и не являются дефектами кода.
