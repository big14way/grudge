#!/usr/bin/env bash
# GRUDGE deletion test. The hackathon gate, run locally.
#
# Judges delete the Sibyl Memory layer and re-run. If GRUDGE still does what it
# claims, it is disqualified. This script performs that deletion two ways and
# checks the outcome of each:
#
#   Phase 1  memory UP      broker refuses the provider that burned it
#   Phase 2  memory STOPPED broker cannot rank, price or set terms -> exit 3
#   Phase 3  memory WIPED   fresh empty DB: the grudge is gone, broker hires the
#                           burned provider again at stranger terms
#
# Phase 2 proves the architecture fails without memory. Phase 3 proves the
# refusal in phase 1 came from memory and nothing else.
#
# Usage: scripts/deletion_test.sh            (from repo root)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PORT="${GRUDGE_TEST_PORT:-7412}"
WORK="$(mktemp -d)"
DB="$WORK/memory.db"
BURN="0x2222222222222222222222222222222222222222"
export GRUDGE_MEMORY_URL="http://127.0.0.1:$PORT"
export SIBYL_MEMORY_TELEMETRY=0
SVC_PID=""
FAILED=0

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
pass() { printf '\033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$*"; FAILED=1; }

start_service() {
  "$PY" -m grudge_memory --db "$DB" --port "$PORT" > "$WORK/service.log" 2>&1 &
  SVC_PID=$!
  for _ in $(seq 1 40); do
    curl -sf "$GRUDGE_MEMORY_URL/health" >/dev/null 2>&1 && return 0
    sleep 0.1
  done
  echo "memory service did not start"; cat "$WORK/service.log"; exit 1
}
stop_service() {
  if [ -n "$SVC_PID" ] && kill -0 "$SVC_PID" 2>/dev/null; then
    kill "$SVC_PID"; wait "$SVC_PID" 2>/dev/null || true
  fi
  SVC_PID=""
}
trap 'stop_service; rm -rf "$WORK"' EXIT

decide() {  # sets CHOSEN (address, NONE, or empty) and RC (broker exit code)
  (cd "$ROOT/broker" && node src/cli.js decide --category research --budget 0.02 --pool pools/sample.json --json >"$WORK/decision.json" 2>"$WORK/broker.err")
  RC=$?
  CHOSEN=""
  if [ "$RC" -eq 0 ]; then
    CHOSEN=$("$PY" -c 'import sys,json; d=json.load(open(sys.argv[1])); print(d["chosen"]["address"] if d["chosen"] else "NONE")' "$WORK/decision.json")
  fi
}

say "Phase 1: memory service UP at $GRUDGE_MEMORY_URL, db $DB"
start_service
echo "seeding: $BURN burns broker-a twice (spec failures on research jobs 9001 and 9002)"
(cd "$ROOT/broker" && node src/cli.js simulate --provider "$BURN" --job 9001 --score 0.2 >/dev/null && \
                      node src/cli.js simulate --provider "$BURN" --job 9002 --score 0.1 >/dev/null)
grep -E "PROMOTE|consortium" "$WORK/service.log" | sed 's/^/  /'
decide
(cd "$ROOT/broker" && node src/cli.js decide --category research --budget 0.02 --pool pools/sample.json 2>/dev/null | sed 's/^/  /')
if [ "$RC" -eq 0 ] && [ "$CHOSEN" != "$BURN" ] && [ "$CHOSEN" != "NONE" ]; then
  pass "with memory, broker passed over $BURN (public 0.97) and hired $CHOSEN"
else
  fail "with memory, expected a hire that is not $BURN, got '$CHOSEN' (rc $RC)"
fi

say "Phase 2: memory service STOPPED (pid $SVC_PID)"
stop_service
decide
sed 's/^/  /' "$WORK/broker.err"
if [ "$RC" -eq 3 ] && [ -z "$CHOSEN" ]; then
  pass "without memory the broker cannot rank, price or set terms: exit code 3, no decision"
else
  fail "without memory, expected exit 3 and no decision, got rc $RC chosen '$CHOSEN'"
fi

say "Phase 3: memory WIPED (rm $DB*), service restarted on an empty layer"
rm -f "$DB" "$DB-wal" "$DB-shm"
start_service
decide
(cd "$ROOT/broker" && node src/cli.js decide --category research --budget 0.02 --pool pools/sample.json 2>/dev/null | sed 's/^/  /')
if [ "$RC" -eq 0 ] && [ "$CHOSEN" = "$BURN" ]; then
  pass "with memory wiped the grudge is gone: broker hires $BURN again, the top public score, at stranger terms"
else
  fail "with memory wiped, expected the broker to hire $BURN, got '$CHOSEN' (rc $RC)"
fi

say "Result"
if [ "$FAILED" -eq 0 ]; then
  pass "all three phases. GRUDGE's decisions exist only while its memory does."
  exit 0
else
  fail "see above"
  exit 1
fi
