# GRUDGE session handoff

## What this is
Broker agent for Virtuals ACP whose private Sibyl Memory of counterparties drives
WHO to hire, WHAT terms, WHAT price. Must FAIL without memory (hackathon gate).
Full brief lives in the first commit's conversation; key constraints repeated here.

## Hard constraints
- Python memory service is the ONLY writer of the SQLite file. Node brokers are HTTP clients.
- sibyl-memory-client 0.8.0 (brief said 0.7.0; 0.8.0 is what pip installs, API identical).
  Verified from source: set_entity(category, name, body, *, status), get_entity raises
  NotFoundError, list_entities(category, *, status, limit), archive_entity has NO restore,
  write_event(*, evaluated, acted, forward, extra, ts), read_events(*, limit, since, until)
  has NO provider filter -> per-provider journal reads go through search(addr, tiers=("journal",)).
  get_reference returns body as a JSON STRING. status is a free string (no enum check).
  Telemetry heartbeat is fire-and-forget, disable with SIBYL_MEMORY_TELEMETRY=0.
- Never use learn()/learner()/lint(): paid tier, raise TierGateError.
- Never use archive_entity for status. Use status kwarg.
- No escrow contract. No dashboard until everything passes twice.
- @virtuals-protocol/acp-node-v2 0.1.12 only. Not acp-node v1, not the Python SDK.
- Commitment hash preimage must include chainid AND the registry/contract address.
- Commits: no Co-Authored-By trailer. Push after every step.

## Toolchain
- Python: `.venv` (3.12 via uv). `uv pip install --python .venv/bin/python -r memory-service/requirements.txt`
- Node 26, npm 11.

## State
- [x] Day 1: Sibyl API verified from source, smoke test passed on all planned key shapes.
- [x] docs/TRUST_VECTOR.md proposed. AWAITING USER CONFIRMATION before writing code past it.
- [ ] 1. memory-service: schema, promotion, decay, status transitions, decide endpoint, pytest.
- [ ] 2. scripts/deletion_test.sh
- [ ] 3. broker A, ACP buyer path, first settled job on Base Sepolia. DAY 1 TEST: ungraduated buyer vs graduated provider.
- [ ] 4. broker B, consortium tenant, cross-broker refusal.
- [ ] 5. ERC-8004 read + giveFeedback on Base mainnet.
- [ ] 6. thin terminal UI.
- [ ] README with file:line index of every memory read/write, prior work declaration, docs/DEMO.md.

## Open decisions (see docs/TRUST_VECTOR.md bottom)
1. EWMA alpha / decay half-life / failure TTL values.
2. Demo shows probation after one job but rule is 2 failures: staged job with per-stage evaluation proposed.
3. Price premium shrinks max price AND job size, or job size only.
