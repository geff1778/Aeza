#!/usr/bin/env bash
#
# Тесты логики run.sh, которую нельзя проверить иначе как реальным запуском:
# обработка устаревшего /var/run/docker.pid и выбор префикса docker/sudo.
#
# Запуск:  bash tests/test_run_sh.sh
#
# Тесты используют подменный pidfile (DOCKER_PIDFILE) и НИКОГДА не трогают
# настоящий /var/run/docker.pid и не запускают демон.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASSED=0
FAILED=0

pass() { printf '  OK   %s\n' "$1"; PASSED=$((PASSED + 1)); }
fail() { printf '  FAIL %s\n' "$1"; FAILED=$((FAILED + 1)); }

# shellcheck source=/dev/null
source "$ROOT_DIR/run.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "run.sh: обработка pidfile"

# --- 1. Отсутствующий pidfile: ничего не делаем, выходим с 0 ---------------
export DOCKER_PIDFILE="$TMP/absent.pid"
if cleanup_stale_pidfile; then
  pass "отсутствующий pidfile → 0 (не ошибка)"
else
  fail "отсутствующий pidfile должен давать код 0"
fi

# --- 2. Устаревший pidfile (PID не существует): удаляем ------------------
# PID 4194303 почти наверняка не существует (выше обычного pid_max).
export DOCKER_PIDFILE="$TMP/stale.pid"
printf '4194303\n' >"$DOCKER_PIDFILE"
if cleanup_stale_pidfile; then
  pass "устаревший pidfile → 0"
else
  fail "устаревший pidfile должен давать код 0"
fi
if [ ! -e "$DOCKER_PIDFILE" ]; then
  pass "устаревший pidfile удалён"
else
  fail "устаревший pidfile не удалён"
fi

# --- 3. Живой PID: pidfile НЕ трогаем, код возврата 1 --------------------
# PID 1 (init) существует всегда.
export DOCKER_PIDFILE="$TMP/live.pid"
printf '1\n' >"$DOCKER_PIDFILE"
if cleanup_stale_pidfile; then
  fail "живой PID не должен приводить к удалению pidfile"
else
  pass "живой PID → 1 (pidfile защищён)"
fi
if [ -e "$DOCKER_PIDFILE" ]; then
  pass "pidfile живого процесса сохранён"
else
  fail "pidfile живого процесса был удалён — это опасно"
fi

# --- 4. Мусор в pidfile: не считаем его живым ----------------------------
export DOCKER_PIDFILE="$TMP/garbage.pid"
printf 'not-a-pid\n' >"$DOCKER_PIDFILE"
if cleanup_stale_pidfile; then
  pass "мусорный pidfile → 0 (считается устаревшим)"
else
  fail "мусорный pidfile должен давать код 0"
fi

# --- 5. pid_alive корректно различает PID ---------------------------------
if pid_alive 1; then pass "pid_alive 1 → true"; else fail "pid_alive 1 должно быть true"; fi
if pid_alive 4194303; then fail "pid_alive 4194303 должно быть false"; else pass "pid_alive 4194303 → false"; fi
if pid_alive ""; then fail "pid_alive '' должно быть false"; else pass "pid_alive '' → false"; fi

# --- 6. daemon_reachable возвращает код, а не падает ----------------------
# Здесь важен лишь корректный код возврата, а не результат.
if daemon_reachable; then
  pass "daemon_reachable → 0 (демон доступен)"
else
  pass "daemon_reachable → 1 (демон недоступен, обработано без падения)"
fi

# --- 7. Диагностика печатается и не раскрывает секретов -------------------
export DOCKER_PIDFILE="$TMP/stale.pid"
printf '4194303\n' >"$DOCKER_PIDFILE"
diag_out="$(docker_diagnostics 2>&1 || true)"
if printf '%s' "$diag_out" | grep -q "демон отвечает"; then
  pass "диагностика печатает состояние демона"
else
  fail "диагностика не напечатала состояние демона"
fi
if printf '%s' "$diag_out" | grep -qiE "SECRET_KEY|PASSWORD|TELEGRAM_BOT_TOKEN"; then
  fail "диагностика раскрывает секреты"
else
  pass "диагностика не раскрывает секреты"
fi

echo
printf 'run.sh: PASSED %d  FAILED %d\n' "$PASSED" "$FAILED"
[ "$FAILED" -eq 0 ]
