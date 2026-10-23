# AGENTS.md

Repository-specific knowledge for Invoice Keeper (repo `geff1778/Aeza`).

## What this project is

A recurring-payments / invoice tracker. FastAPI + PostgreSQL backend, React 19
+ Vite frontend, a dedicated notification worker, nginx reverse proxy, Docker
Compose deployment. Product name in the UI is **Invoice Keeper**; the repo is
named **Aeza**.

## Layout

- `backend/app/api/` — routers and dependencies (RBAC lives in `deps.py`)
- `backend/app/services/` — all business logic. Key modules:
  - `status.py` — single source of truth for occurrence status
  - `dates.py` — anchored month arithmetic (`add_months_anchored`)
  - `payments.py` — occurrence queries, `mark_paid`, unmark, completion
  - `notifications.py` — decides what to notify, writes the outbox
  - `dispatcher.py`, `telegram.py`, `email.py` — transports only
- `backend/app/worker/main.py` — the scheduler. Runs as its own process.
- `backend/tests/` — pytest (unit + API integration)
- `frontend/src/styles/tokens.css` — design tokens; `app.css` — everything else
- `frontend/e2e/app.spec.ts` — Playwright; `e2e/helpers.ts` — shared helpers
- `docs/` — ARCHITECTURE.md, DEMO.md, TEST_REPORT.md

## Commands

`./run.sh` is the entry point: it creates `.env`, detects whether `sudo docker`
is needed, waits for API health, and wraps every check.

```bash
./run.sh                # up --build -d + wait for health
./run.sh seed           # synthetic demo data (idempotent)
./run.sh verify         # 57 live HTTP checks against the running stack
./run.sh test           # 106 backend tests (starts its own test DB)
./run.sh e2e            # 42 Playwright tests (desktop + mobile)
./run.sh check          # run.sh tests + build + typecheck + lint
./run.sh full           # up + seed + verify + test + check
./run.sh doctor         # Docker + stack diagnostics (no secrets)
./run.sh creds          # demo credentials from .env
./run.sh logs worker    # follow a service log
./run.sh reset          # down -v (destroys data, asks for confirmation)
```

Raw equivalents, when the wrapper is not wanted:

```bash
docker compose up --build -d
docker compose --profile demo run --rm seed
cd backend && .venv/bin/python -m pytest
cd frontend && npm run build && npm run typecheck && npm run lint
cd frontend && npx playwright test
backend/.venv/bin/python scripts/verify_stack.py
```

## Conventions and gotchas

- **Business dates vs timestamps.** `due_date`/`paid_at` are calendar dates in
  `APP_TIMEZONE` (Europe/Moscow). Technical timestamps are UTC. Use
  `local_today(settings.tz)` — never `date.today()` — for business logic.
- **Never add a per-user paid flag.** Status belongs to the occurrence. This is
  a core product requirement, not an implementation detail.
- **Money is `Numeric`, never `float`.** Currencies are never summed together.
- **Deletion means completion.** `DELETE /recurring-payments/{id}` sets
  `is_active = false`; history must survive.
- **Notification idempotency is enforced in the database** (unique
  `idempotency_key` and unique `(occurrence, channel, kind)`), not in memory.
- **nginx uses `resolver 127.0.0.11` + `$api_upstream`.** Without this it caches
  the API container IP and returns 502 after the API is recreated.
- **E2E must handle the mobile hamburger.** Use `goTo()` / `logout()` from
  `e2e/helpers.ts`; a direct nav-link click fails on narrow viewports.
- **Playwright artifacts (`frontend/test-results/`) contain demo passwords** and
  are gitignored. Do not commit them.
- **`verify_stack.py` needs the demo user.** It logs in as `demo_user`; run
  `./run.sh seed` first or it exits with a clear message telling you to.
- **pytest needs its own PostgreSQL** on `TEST_DB_PORT` (default 55432) with user
  `invoice`. `./run.sh test` starts it in a container; running `pytest` directly
  requires it to exist already. Tests never touch the dev database.
- **Docker usually needs `sudo` here** (the user is not in the `docker` group), so
  `run.sh` resolves `sudo docker` automatically. When the daemon is unreachable it
  prints diagnostics plus fix hints; `./run.sh doctor` shows the same on demand.
  It only ever deletes `/var/run/docker.pid` when the PID inside is dead — a live
  daemon is never disturbed.
- **`tests/test_run_sh.sh` covers that pidfile logic** with a stub pidfile
  (`DOCKER_PIDFILE`) and runs as part of `./run.sh check`. It never touches the
  real `/var/run/docker.pid` and never starts a daemon.

## Demo credentials

Synthetic only, and overridable by env vars:
`admin` / `ADMIN_PASSWORD`, `demo_user` / `DEMO_PASSWORD`.
`scripts/verify_stack.py` reads `VERIFY_ADMIN_*` / `VERIFY_USER_*`.
Never commit a real `.env`.

## Unverified in this environment

Real Telegram and SMTP delivery: no credentials available. The logic is covered
by a mock transport; see `docs/TEST_REPORT.md` before claiming delivery works.
