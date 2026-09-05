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

## Rehearsal 2026-09-03 (grudge-rehearsal.db): FULL SEQUENCE PASSES LIVE
Sandbox 2 = PROVIDER2 0xd82ac03a.. ERC-8004 agent 84571 (its first signer returned 500 from Virtuals; re-adding the signer fixed it).
Session 1 jobs 75859/75860 (burn -> probation), session 2 jobs 75865/75866 (sandbox 2 hired, 5/5), broker B jobs 75867/75868.
Demo pool = broker/pools/demo.json. Clawpump (live third party) is in pools/mainnet.json only; it no-showed on job 75818.

## Live providers (2026-09-04, rehearsal DB)
pools/live.json: blocknuri (overcharged 0.05 on 0.02 quote -> price refusal, jobs 76166/76167 unfunded), COINGAZURA (76168/76169 settled 3/3),
OuroBoroZ (76170/76171 rejected 1/3: OUR task mismatch). blocknuri = ERC-8004 agent 55211: two value-0 ratings revoked (idx 1,2).
Rule now: price refusal -> action "refused", score null, charged=set budget, no giveFeedback, no retry. Journal keeps evaluated.sample.
Rehearsal DB still shows blocknuri/OuroBoroZ on probation from those runs; the demo uses a fresh DB.

## Counterfactual (2026-09-04)
decide() returns `counterfactual` (memoryless pick = top public score, flat terms) and logs "MEMORYLESS would hire ..."
render.js prints WITHOUT MEMORY / WITH MEMORY lines. Session 3 (jobs 76085, 76087) promoted sandbox 2 to trusted;
dry-run then shows single stage, no evaluator, retries 2, cap 0.7125. README section 2 has the session table.

## Demo recorded 2026-09-05 (grudge-demo.db, still running on 7411 with both sandbox providers)
Session 1 jobs 76435/76436 (burned, probation), session 2 jobs 76441/76442 (sandbox 2 hired 5/5), session 3 jobs 76489/76490 (sandbox 2 TRUSTED),
broker B jobs 76447/76448 (refused sandbox 1 on consortium, hired sandbox 2). Six giveFeedback txs from the feedback EOA. README section 7 has the links.
erc8004.js now loads .env standalone (the score command returned agentId null before that fix).

## Demo state
~/.sibyl-memory/grudge.db holds real memory: provider 0x39d04d78 is BLACKLISTED (3 live failures: jobs 75666, 75667, 75668) until ~2026-10-02.
Refund observation verified live on job 75668 (refund_behavior -> 1.0).
For a fresh demo run use a new --db path. broker A ~0.98 USDC, broker B 0.5 USDC, feedback EOA ~0.00015 ETH.
BASE_RPC_URL=https://mainnet.base.org (publicnode rejects fresh receipts).

## Submission checklist (rules at hack.sibyllabs.org/rules, deadline Sep 10 23:59 UTC)
- [x] Public repo, MIT, real commit history
- [x] README: function, memory load-bearing location (sec 11), partner stacks (sec 6), how memory made this possible (sec 2), Prior Work declaration (sec 13, names no other project by user decision)
- [x] Demo video 3:50 built 2026-09-05: ~/Desktop/grudge-demo.mp4 (NOT in the repo, do not commit). Sources: ~/Desktop/shot*.mov, ~/Desktop/voiceboxgenerations, build script ~/Desktop/grudge-demo/build.py
- [ ] Two public posts tagging @sibylcap + partners: demo video + build log (drafts moved out of the repo to ~/Desktop/grudge-demo/POSTS.md)
- [ ] Build page: team, stacks (Base, Virtuals), memory implementation note (answers drafted in chat 2026-09-03)
- [ ] PMF evidence: only real usage claimed; design partners / waitlist would need real, verifiable artifacts

## Next
- Landing page for the memory service UI (requested 2026-09-05): served at /, motion design, how it works, repo link; /ui stays the viewer.
- Keep README key-site line numbers in sync with store.py (scripts/memory_index.py).

## Previously blocked (resolved 2026-09-02)
Three Virtuals ACP wallets (broker A, broker B, sandbox provider) in broker/.env. Then, in order:
1. DAY 1 TEST: `node src/hire.js --browse research --budget 0.05` on Base Sepolia against a graduated live provider.
   If create+fund fails for an ungraduated buyer, use only our sandbox provider (node src/provider.js).
2. Register the sandbox provider on the Service Registry with offering "GRUDGE Research Brief" at 0.01 USDC.
3. First settled job on Sepolia, then mainnet with $0.01 and --feedback for the giveFeedback tx.
4. Record the demo (done 2026-09-05).

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
- [x] README (problem lives IN the README, no separate problem doc), docs/MEMORY_INDEX.md (regenerate with scripts/memory_index.py after editing store.py; README key-site line numbers must be refreshed too). docs/DEMO.md and docs/POSTS.md were removed from the repo on 2026-09-05 (archived on the Desktop).
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
