# GRUDGE demo script (2 to 5 minutes, one unedited take, clock on screen)

Screen layout: left = memory service (`[MEMORY]` log), right = broker,
and a browser window on `http://127.0.0.1:7411/ui` (the memory viewer: trust
vectors, consortium signals, journal, live log). Keep a clock visible; the
viewer's header shows the service clock too.

Before recording:
```
.venv/bin/python -m grudge_memory --db ~/.sibyl-memory/grudge-demo.db        # left pane, FRESH DB path
cd broker && node src/provider.js --agent PROVIDER  --mode burn               # sandbox 1, separate terminal
cd broker && node src/provider.js --agent PROVIDER2 --mode good               # sandbox 2, separate terminal
open http://127.0.0.1:7411/ui                                                 # memory viewer
```
Rehearsed live on Base mainnet 2026-09-02 (jobs 75664 to 75667). Each session
costs 0.01 USDC per stage; rejected stages refund.

## 0:00 Problem
Public reputation is one number everyone shares and games. ERC-8004 gives
every buyer the same score for a provider. Show BaseScan getSummary for a
real agent id (`node src/erc8004.js score <wallet>`): one number, 39 raters,
none of them you.

## 0:30 Session 1: GRUDGE hires the top public score and gets burned
```
node src/hire.js --tenant broker-a --category research --budget 0.02 --pool pools/demo.json --feedback
```
- The ranking table: all candidates `unknown`, the sandbox provider has the
  highest public score, terms engine gives STAGED (2x), evaluator required,
  retry 1, cap 10% of base size.
- ACP: job created, budget.set, fund (tx hash on screen), job.submitted.
- `[GRUDGE] evaluated against REFERENCE spec:research: score 0.2, unmet [...]`,
  reject, outcome recorded.
- Stage 2 runs (retry budget 1), misses again.
- Left pane: `[MEMORY] write ... PROMOTE journal -> entity ... status=probation`
  and `tenant=consortium signal ... redacted`.

## 1:30 Kill the broker
Ctrl-C the broker pane. Show the empty terminal. The memory service stays up.

## 1:45 Session 2: cold start, same pool, GRUDGE refuses and names the job
```
node src/hire.js --tenant broker-a --category research --budget 0.02 --pool pools/demo.json --feedback
```
- Same candidates. Sandbox 1 now shows `probation`, verdict REFUSE, reason
  `burned us on job <id> on <date>; public score 0.97 ignored`.
- GRUDGE hires sandbox 2 (public 0.85) on probe terms; both stages pass 5/5.
  That is the WHO decision on screen: the lower public number wins.
DO NOT CUT HERE.

## 2:30 Deletion test, live
```
scripts/deletion_test.sh
```
Three phases on screen: memory up (refuses), memory stopped (exit 3, cannot
rank, price or set terms), memory wiped (hires the burned provider again).
For the camera, also Ctrl-C the demo memory service once: the viewer flips
to "MEMORY LAYER GONE" within two seconds. Restart it afterwards.

## 3:00 Broker B, separate process, never met the provider
```
GRUDGE_TENANT=broker-b node src/hire.js --agent BROKER_B --category research --budget 0.02 --pool pools/demo.json
```
- `broker-b` private view: unknown. Consortium: 2 live failures reported by
  broker-a. Verdict REFUSE, reason starts with `consortium:`.
- Left pane shows the read on `tenant=consortium signal/...`.

## 3:30 BaseScan
- ACP Create Job and Fund tx hashes from session 1 (printed by `[CHAIN]`).
- `giveFeedback` tx on Base mainnet from `--feedback`: value = evaluator
  score, tag1 `grudge`, tag2 `research`, feedbackHash = the memory
  commitment (chainid + registry bound). Provider is ERC-8004 agent 84165;
  `node src/erc8004.js score 0x39d04d783e7d0a969c1c585ad26c3a5faaafee6f`
  shows the public number moving after our feedback.

## Fallbacks
- If a live provider stalls, the sandbox provider is the critical path.
  Never wait on graduation.
- If ACP is down, `scripts/deletion_test.sh` and `scripts/consortium_test.sh`
  show the memory behaviour end to end with two real Node processes.
