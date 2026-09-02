#!/usr/bin/env bash
# Cross-broker coordination through the "consortium" tenant.
#
# Broker A (one Node process) gets burned twice by a provider and records the
# private outcome in tenant broker-a plus a REDACTED signal in tenant
# consortium. Broker B (a second Node process, tenant broker-b, never met the
# provider) reads only the consortium signal and refuses.
#
# Both processes talk to the same single-writer Python memory service, so
# there is no lock contention on the SQLite file.
#
# Usage: scripts/consortium_test.sh   (uses --simulate outcomes; with ACP
#        credentials the same flow happens through real jobs via hire.js)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PORT="${GRUDGE_TEST_PORT:-7413}"
WORK="$(mktemp -d)"
BURN="0x2222222222222222222222222222222222222222"
export GRUDGE_MEMORY_URL="http://127.0.0.1:$PORT"
export SIBYL_MEMORY_TELEMETRY=0
FAILED=0
say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
pass() { printf '\033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$*"; FAILED=1; }

"$PY" -m grudge_memory --db "$WORK/memory.db" --port "$PORT" > "$WORK/service.log" 2>&1 &
SVC=$!
trap 'kill $SVC 2>/dev/null; wait $SVC 2>/dev/null; rm -rf "$WORK"' EXIT
for _ in $(seq 1 40); do curl -sf "$GRUDGE_MEMORY_URL/health" >/dev/null 2>&1 && break; sleep 0.1; done

say "Broker A (pid of its own node process below) is burned twice by $BURN"
(cd "$ROOT/broker" && GRUDGE_TENANT=broker-a node src/cli.js simulate --provider "$BURN" --job 7001 --score 0.2 2>&1 | sed 's/^/  A: /')
(cd "$ROOT/broker" && GRUDGE_TENANT=broker-a node src/cli.js simulate --provider "$BURN" --job 7002 --score 0.1 2>&1 | sed 's/^/  A: /')
grep -E "consortium" "$WORK/service.log" | sed 's/^/  /'

say "What the consortium holds (redacted: no price, no job id, no spec text)"
SIG=$(curl -s "$GRUDGE_MEMORY_URL/consortium/$BURN")
echo "  $SIG"
if echo "$SIG" | grep -q '"live_failures": 2' && ! echo "$SIG" | grep -Eq 'price|acp_job_id|unmet|notes'; then
  pass "consortium signal is redacted and carries 2 live failures from broker-a"
else
  fail "consortium signal wrong: $SIG"
fi

say "Broker B, separate node process, tenant broker-b, has never met $BURN"
B_PRIVATE=$(curl -s -H "X-Grudge-Tenant: broker-b" "$GRUDGE_MEMORY_URL/counterparty/$BURN")
echo "  broker-b private view: $B_PRIVATE"
OUT=$(cd "$ROOT/broker" && GRUDGE_TENANT=broker-b node src/cli.js decide --category research --budget 0.02 --pool pools/sample.json 2>/dev/null)
echo "$OUT" | sed 's/^/  B: /'
if echo "$B_PRIVATE" | grep -q '"status": "unknown"' && echo "$OUT" | grep -q "consortium: 2 live failures" && ! echo "$OUT" | grep -q "HIRE $BURN"; then
  pass "broker B refused $BURN on the consortium signal alone"
else
  fail "broker B did not refuse via consortium"
fi
grep -E "tenant=consortium signal.*read|DECIDE" "$WORK/service.log" | tail -3 | sed 's/^/  /'

say "Result"
[ "$FAILED" -eq 0 ] && pass "cross-broker refusal through the consortium tenant" || fail "see above"
exit $FAILED
