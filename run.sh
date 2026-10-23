#!/usr/bin/env bash
#
# Invoice Keeper — единый скрипт запуска и проверки.
#
# Быстрый старт:
#   ./run.sh              поднять стек (сборка + миграции + bootstrap админа)
#   ./run.sh seed         создать демонстрационные данные
#
# Проверка:
#   ./run.sh verify       проверить запущенный стек по HTTP (57 проверок)
#   ./run.sh test         backend-тесты (pytest, 101 тест)
#   ./run.sh e2e          браузерные тесты (Playwright, 42 теста)
#   ./run.sh check        статические проверки (build, typecheck, lint)
#   ./run.sh full         up + seed + verify + test + check
#
# Обслуживание:
#   ./run.sh ps           состояние контейнеров
#   ./run.sh logs [svc]   логи сервиса (api|worker|frontend|postgres)
#   ./run.sh creds        показать демо-учётные данные из .env
#   ./run.sh open         открыть веб-панель в браузере
#   ./run.sh down         остановить (данные сохраняются)
#   ./run.sh reset        остановить и УДАЛИТЬ данные (volumes)
#   ./run.sh help         эта справка
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"
BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_DB_PORT="${TEST_DB_PORT:-55432}"
TEST_DB_CONTAINER="ik-test-pg"

# Префикс запуска Docker. Там, где пользователь не в группе docker,
# автоматически становится "sudo docker".
DOCKER=(docker)
COMPOSE=()

# ---------------------------------------------------------------- вывод
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; RESET=''
fi
info()  { printf '%s\n' "${BLUE}==>${RESET} $*"; }
ok()    { printf '%s\n' "${GREEN} OK ${RESET} $*"; }
warn()  { printf '%s\n' "${YELLOW}!!${RESET} $*" >&2; }
fail()  { printf '%s\n' "${RED}ОШИБКА:${RESET} $*" >&2; exit 1; }
title() { printf '\n%s\n' "${BOLD}$*${RESET}"; }

# ---------------------------------------------------------------- Docker
resolve_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker не установлен. См. https://docs.docker.com/engine/install/"

  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    # daemon работает, но нужен sudo: пользователь не в группе docker
    DOCKER=(sudo docker)
    warn "Использую 'sudo docker' (пользователь не в группе docker)"
    warn "Убрать sudo: sudo usermod -aG docker \$USER  (затем перелогиниться)"
  else
    warn "Docker daemon недоступен, пробую запустить..."
    if command -v sudo >/dev/null 2>&1; then
      sudo -n dockerd >/tmp/dockerd-invoice-keeper.log 2>&1 &
      for _ in $(seq 1 30); do
        sleep 1
        sudo -n docker info >/dev/null 2>&1 && break
      done
    fi
    if sudo -n docker info >/dev/null 2>&1; then
      DOCKER=(sudo docker)
    elif docker info >/dev/null 2>&1; then
      DOCKER=(docker)
    else
      fail "Docker daemon не запускается. Запустите вручную: sudo dockerd &"
    fi
  fi

  if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
    COMPOSE=("${DOCKER[@]}" compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    fail "Не найден 'docker compose'. Установите Docker Compose v2."
  fi
}

# ---------------------------------------------------------------- .env
gen_secret() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -d '\n'
  else
    fail "Нужен python3 или openssl для генерации SECRET_KEY."
  fi
}

ensure_env() {
  if [ -f "$ENV_FILE" ]; then
    ok ".env уже существует — оставляю без изменений"
    return 0
  fi

  [ -f "$ENV_EXAMPLE" ] || fail "Не найден $ENV_EXAMPLE"
  command -v python3 >/dev/null 2>&1 || fail "Для создания .env нужен python3"

  info "Создаю .env из $ENV_EXAMPLE со случайным SECRET_KEY"
  local secret
  secret="$(gen_secret)"

  python3 - "$secret" <<'PY'
import pathlib, sys

(secret,) = sys.argv[1:]
src = pathlib.Path(".env.example").read_text(encoding="utf-8")

# Секрет сессий всегда уникален. Учётные данные остаются демонстрационными,
# чтобы ./run.sh seed, ./run.sh verify и docs/DEMO.md были согласованы.
replacements = {"SECRET_KEY": secret}

out = []
for line in src.splitlines():
    key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
    out.append(f"{key}={replacements[key]}" if key in replacements else line)

pathlib.Path(".env").write_text("\n".join(out) + "\n", encoding="utf-8")
PY

  ok ".env создан (SECRET_KEY сгенерирован случайно)"
  warn "Учётные данные в .env — демонстрационные. Смените их перед реальным использованием:"
  warn "  ADMIN_PASSWORD и DEMO_PASSWORD в .env, затем ./run.sh reset && ./run.sh && ./run.sh seed"
}

env_value() {
  [ -f "$ENV_FILE" ] || return 1
  sed -n "s/^$1=//p" "$ENV_FILE" | head -1
}

# ---------------------------------------------------------------- окружения
ensure_backend_venv() {
  if [ -x backend/.venv/bin/python ]; then return 0; fi
  command -v python3 >/dev/null 2>&1 || fail "Нужен python3 для backend/.venv"
  info "Создаю backend/.venv и ставлю зависимости (один раз)"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --quiet --upgrade pip
  backend/.venv/bin/pip install --quiet \
    -r backend/requirements.txt -r backend/requirements-dev.txt
  ok "Зависимости backend установлены"
}

ensure_frontend_modules() {
  if [ -d frontend/node_modules ]; then return 0; fi
  command -v npm >/dev/null 2>&1 || fail "Нужен npm для frontend"
  info "Ставлю frontend-зависимости (один раз)"
  ( cd frontend && npm ci )
}

# ---------------------------------------------------------------- ожидание
wait_for_health() {
  local url="$BASE_URL/api/v1/health"
  info "Жду готовности API ($url)"
  for i in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      ok "API отвечает (попытка $i)"
      return 0
    fi
    sleep 2
  done
  warn "API не ответил за 120 секунд. Логи: ./run.sh logs api"
  return 1
}

wait_for_db() {
  info "Жду готовности тестовой БД на порту $TEST_DB_PORT"
  for _ in $(seq 1 40); do
    if "${DOCKER[@]}" exec "$TEST_DB_CONTAINER" pg_isready -U invoice >/dev/null 2>&1; then
      ok "Тестовая БД готова"
      return 0
    fi
    sleep 2
  done
  fail "Тестовая БД не поднялась"
}

# ---------------------------------------------------------------- команды
cmd_up() {
  resolve_docker
  ensure_env

  title "Сборка и запуск"
  "${COMPOSE[@]}" up --build -d

  wait_for_health || true

  title "Состояние"
  "${COMPOSE[@]}" ps

  print_access
}

cmd_seed() {
  resolve_docker
  ensure_env
  title "Демонстрационные данные"
  info "Данные синтетические и идемпотентные — повторный запуск безопасен"
  "${COMPOSE[@]}" --profile demo run --rm seed
  ok "Демо-данные созданы"
  cmd_creds
}

cmd_verify() {
  title "Проверка запущенного стека"
  ensure_backend_venv
  backend/.venv/bin/python scripts/verify_stack.py "$BASE_URL"
}

cmd_test() {
  title "Backend-тесты (pytest)"
  resolve_docker
  ensure_backend_venv
  ensure_test_db
  ( cd backend && .venv/bin/python -m pytest )
}

ensure_test_db() {
  if "${DOCKER[@]}" exec "$TEST_DB_CONTAINER" pg_isready -U invoice >/dev/null 2>&1; then
    ok "Тестовая БД уже запущена"
    return 0
  fi
  info "Поднимаю отдельную тестовую БД (рабочую базу не трогает)"
  "${DOCKER[@]}" rm -f "$TEST_DB_CONTAINER" >/dev/null 2>&1 || true
  "${DOCKER[@]}" run -d --name "$TEST_DB_CONTAINER" \
    -e POSTGRES_USER=invoice -e POSTGRES_PASSWORD=invoice -e POSTGRES_DB=invoice \
    -p "${TEST_DB_PORT}:5432" postgres:16-alpine >/dev/null
  wait_for_db
}

cmd_e2e() {
  title "Браузерные тесты (Playwright)"
  wait_for_health || fail "Стек не запущен. Сначала: ./run.sh && ./run.sh seed"
  ensure_frontend_modules
  ( cd frontend && npx playwright install chromium >/dev/null 2>&1 || true )
  ( cd frontend && npx playwright test )
}

cmd_check() {
  title "Статические проверки frontend"
  ensure_frontend_modules
  ( cd frontend && npm run build && npm run typecheck && npm run lint )
  ok "Сборка, типы и линтер без ошибок"
}

cmd_full() {
  cmd_up
  cmd_seed
  cmd_verify
  cmd_test
  cmd_check
  title "Итог"
  ok "Все проверки пройдены"
}

cmd_ps() {
  resolve_docker
  "${COMPOSE[@]}" ps
}

cmd_logs() {
  resolve_docker
  local svc="${1:-}"
  if [ -z "$svc" ]; then
    "${COMPOSE[@]}" logs -f --tail=100
  else
    "${COMPOSE[@]}" logs -f --tail=200 "$svc"
  fi
}

cmd_creds() {
  title "Учётные данные (из .env)"
  local admin_user admin_pass demo_user demo_pass
  admin_user="$(env_value ADMIN_USERNAME || echo admin)"
  admin_pass="$(env_value ADMIN_PASSWORD || echo '')"
  demo_user="$(env_value DEMO_USERNAME || echo demo_user)"
  demo_pass="$(env_value DEMO_PASSWORD || echo '')"

  printf '  %-24s %s\n' "Администратор:" "$admin_user"
  printf '  %-24s %s\n' "Пароль администратора:" "$admin_pass"
  printf '  %-24s %s\n' "Обычный пользователь:" "$demo_user"
  printf '  %-24s %s\n' "Пароль пользователя:" "$demo_pass"
  printf '\n  %s\n' "${DIM}Обычный пользователь появляется после: ./run.sh seed${RESET}"
  printf '  %s\n' "${DIM}Смените пароли перед реальным использованием.${RESET}"
}

cmd_open() {
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$BASE_URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$BASE_URL" >/dev/null 2>&1 &
  else info "Откройте вручную: $BASE_URL"; fi
}

cmd_down() {
  resolve_docker
  info "Останавливаю контейнеры (данные в volumes сохраняются)"
  "${COMPOSE[@]}" down
  ok "Остановлено"
}

cmd_reset() {
  resolve_docker
  warn "Это УДАЛИТ базу и загруженные чеки (volumes)."
  printf 'Продолжить? Введите "yes": '
  read -r answer
  [ "$answer" = "yes" ] || { info "Отменено"; return 0; }
  "${COMPOSE[@]}" down -v
  "${DOCKER[@]}" rm -f "$TEST_DB_CONTAINER" >/dev/null 2>&1 || true
  ok "Всё удалено"
}

print_access() {
  title "Доступ"
  printf '  %-16s %s\n' "Веб-панель:"   "$BASE_URL"
  printf '  %-16s %s\n' "Swagger UI:"   "$BASE_URL/api/v1/docs"
  printf '  %-16s %s\n' "OpenAPI JSON:" "$BASE_URL/api/v1/openapi.json"
  printf '  %-16s %s\n' "Healthcheck:"  "$BASE_URL/api/v1/health"
  printf '\n  %s\n' "${DIM}Демо-данные: ./run.sh seed${RESET}"
}

cmd_help() {
  sed -n '3,24p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- dispatch
case "${1:-up}" in
  up|"")       cmd_up ;;
  seed|demo)   cmd_seed ;;
  verify)      cmd_verify ;;
  test|tests)  cmd_test ;;
  e2e)         cmd_e2e ;;
  check)       cmd_check ;;
  full|all)    cmd_full ;;
  ps|status)   cmd_ps ;;
  logs)        shift; cmd_logs "${1:-}" ;;
  creds|credentials) cmd_creds ;;
  open)        cmd_open ;;
  down|stop)   cmd_down ;;
  reset)       cmd_reset ;;
  help|-h|--help) cmd_help ;;
  *)
    warn "Неизвестная команда: $1"
    echo
    cmd_help
    exit 1
    ;;
esac
