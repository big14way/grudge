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

## ACP facts verified live (2026-09-02 evening)
- Wallets: broker A 0x1e8ad4f3.., broker B 0x36d32488.., provider 0x39d04d78.. (agent name "GRUDGE Research", NO offering yet).
- Base Sepolia is UNUSABLE: Virtuals wallet proxy rejects the Sepolia ACP contract "not on the sponsored allowlist". Mainnet only.
- Any non-ACP call from the sponsored wallet is rejected the same way (USDC transfer, ERC-8004 giveFeedback, mint).
  => giveFeedback goes from a plain EOA: FEEDBACK_PRIVATE_KEY / FEEDBACK_ADDRESS in .env (needs a little ETH on Base).
  => USDC must be sent to each broker wallet directly by the user.
- DAY 1 TEST PASSED on mainnet: broker A (ungraduated) createJob -> job 75652, tx 0xdf2db6699866bcfee2d7a39ec1462e37408540b55e93f2aa70830d85f967859f. Left unfunded, expires.
- hire.js falls back to raw createJob + requirement message when the candidate has no offering (pools/mainnet.json).

## Demo state
~/.sibyl-memory/grudge.db holds real memory: provider 0x39d04d78 is BLACKLISTED (3 live failures: jobs 75666, 75667, 75668) until ~2026-10-02.
Refund observation verified live on job 75668 (refund_behavior -> 1.0).
For a fresh demo run use a new --db path. broker A ~0.98 USDC, broker B 0.5 USDC, feedback EOA ~0.00015 ETH.
BASE_RPC_URL=https://mainnet.base.org (publicnode rejects fresh receipts).

## Next
- docs/DEMO.md recording. Optional: hire a live third-party provider via --browse for the "hire real providers where possible" line.
- Keep README key-site line numbers in sync with store.py (scripts/memory_index.py).

## Previously blocked (resolved 2026-09-02)
Three Virtuals ACP wallets (broker A, broker B, sandbox provider) in broker/.env. Then, in order:
1. DAY 1 TEST: `node src/hire.js --browse research --budget 0.05` on Base Sepolia against a graduated live provider.
   If create+fund fails for an ungraduated buyer, use only our sandbox provider (node src/provider.js).
2. Register the sandbox provider on the Service Registry with offering "GRUDGE Research Brief" at 0.01 USDC.
3. First settled job on Sepolia, then mainnet with $0.01 and --feedback for the giveFeedback tx.
4. Record docs/DEMO.md.

## Toolchain
- Python: `.venv` (3.12 via uv). `uv pip install --python .venv/bin/python -r memory-service/requirements.txt`
- Node 26, npm 11.

## State
- [x] Day 1: Sibyl API verified from source, smoke test passed on all planned key shapes.
- [x] docs/TRUST_VECTOR.md CONFIRMED by user (all three open decisions, recommended options).
- [x] 1. memory-service: trust.py (pure math), store.py (every memory read/write, [MEMORY] log),
      evaluator.py (deterministic spec scoring from REFERENCE tier), keccak.py (commitment),
      server.py (stdlib HTTP, port 7411), 31 pytest passing. `pip install -e memory-service`.
      Run: `.venv/bin/python -m grudge_memory --db PATH --port 7411`
- [x] 2. scripts/deletion_test.sh: 3 phases (memory up -> refuse burned; stopped -> exit 3; wiped -> re-hires burned). PASSES.
      broker/src/memory.js is the only door to memory, no local ranking. broker/src/cli.js: decide|simulate|show|multi.
- [x] 3. LIVE ON MAINNET 2026-09-02: jobs 75664/75665 settled, 75666/75667 rejected (session 1). broker/src/hire.js (buyer path: decide -> createJobByOfferingName -> fund <= max_price -> evaluate -> complete/reject -> outcome),
      broker/src/provider.js (sandbox seller, PROVIDER_MODE good|burn|overcharge), broker/src/acp.js (agent factory, tx hash tracing),
      broker/src/erc8004.js (publicScore read via getClients+getSummary, giveFeedback via adapter.sendCalls, owner index cached in broker/.cache).
      Dry run passes. NOT YET RUN AGAINST ACP: needs three Virtuals wallets in broker/.env (see .env.example).
      DAY 1 TEST still pending: `node src/hire.js --browse research --budget 0.05 --tenant broker-a` on Base Sepolia.
- [x] 4. scripts/consortium_test.sh: broker A (node) burned twice -> consortium signal; broker B (separate node, tenant broker-b) refuses. PASSES.
      Live ACP version = same flow via hire.js with --tenant broker-b --agent BROKER_B.
- [x] 5. ERC-8004: provider registered as agent 84165 (identity EOA in .env). giveFeedback sent 4x from FEEDBACK EOA. See README live table.
- [x] 6. thin UI: broker/src/render.js (terminal) + memory-service/grudge_memory/ui.html served at /ui by the memory service
      (GET /snapshot, GET /log?after=N; viewer reads bypass _mem so they never count or trigger decay). Screenshot verified via headless Brave.
- [x] README (problem lives IN the README, no separate problem doc), docs/MEMORY_INDEX.md (regenerate with scripts/memory_index.py after editing store.py; README key-site line numbers must be refreshed too), docs/DEMO.md.
- NO prior-work declaration anywhere (removed by user 2026-09-03). Do not cite any other project in the repo.

## Decisions locked (docs/TRUST_VECTOR.md bottom)
alpha 0.35 / half-life 14d / TTL 30d; staged job with per-stage evaluation for demo session 1;
premium shrinks max price AND job size. Probation = refused in the failed category only.

## ERC-8004 facts verified live on Base (2026-09-02)
Identity 0x8004A169.. and Reputation 0x8004BAa1.. are ERC-1967 proxies (impl 0x7274e874.., 0x16e0fa7f..).
getSummary REVERTS with "clientAddresses required" on an empty list -> read getClients(agentId) first.
Values are 0..100 scale, decimals 0 (agent 1: 39 feedbacks, mean 81). getAgentWallet NOT deployed.
~84k agents; public RPCs reject eth_getLogs over ~10k blocks, so wallet->agentId uses a multicall ownerOf index.

## HTTP API (memory-service/grudge_memory/server.py docstring)
POST /decide {job:{category,budget_usdc}, candidates:[{address,public_score,quoted_price_usdc}]}
POST /evaluate {category, delivery} -> {score, unmet, ...}
POST /outcome {provider, acp_job_id, category, score, action, quoted/charged, latency_s, sla_s, tx_hash, chain_id, broker_wallet, evaluation, lesson}
POST /inflight, GET /counterparty/<addr>, GET /consortium/<addr>, GET /journal/<addr>, POST /query/multi {query}
Tenant via X-Grudge-Tenant header.
