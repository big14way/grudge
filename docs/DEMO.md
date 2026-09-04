# GRUDGE demo: production script

Target length 3:00. Hard limits from the rules: 2 to 5 minutes, one fresh-session
recall moment that is unmistakable, problem, audience, product, mechanics, Sibyl
Memory usage, and the load-bearing moment. Recorded first, narrated second,
assembled in Remotion.

Contents
1. [Setup before recording](#1-setup-before-recording)
2. [Shot list: what to record](#2-shot-list-what-to-record)
3. [Narration: what to say, word for word](#3-narration-word-for-word)
4. [Captions and title cards](#4-captions-and-title-cards)
5. [Remotion assembly order](#5-remotion-assembly-order)
6. [Rules checklist](#6-rules-checklist)

---

## 1. Setup before recording

Record every shot at 1920x1080 or larger, dark terminal theme, font size 16
or larger so text is legible after scaling. Keep the OS clock visible in the
menu bar in every capture: the rules ask for a timestamp on screen and the
memory viewer's header clock adds a second one.

Open five windows and lay them out before you press record:

| window | command | purpose |
|--------|---------|---------|
| A, memory service | `cd ~/Developer/grudge && .venv/bin/python -m grudge_memory --db ~/.sibyl-memory/grudge-demo.db --port 7411` | left half. `[MEMORY]` log. The DB path MUST NOT EXIST yet. |
| B, broker | `cd ~/Developer/grudge/broker` and wait | right half. Every hire runs here. |
| C, sandbox 1 | `cd ~/Developer/grudge/broker && node src/provider.js --agent PROVIDER --mode burn` | small, can be hidden. Misses the spec on purpose. |
| D, sandbox 2 | `cd ~/Developer/grudge/broker && node src/provider.js --agent PROVIDER2 --mode good` | small, can be hidden. Delivers to spec. |
| E, browser | `http://127.0.0.1:7411/ui` | the memory viewer, full screen for its own shots. |

Confirm before recording:

```
cd ~/Developer/grudge/broker
node src/wallet.js whoami          # four agents authenticate, broker A has USDC on Base
ls ~/.sibyl-memory/grudge-demo.db  # must say "No such file"
```

If anything went wrong mid-take: stop A, delete `~/.sibyl-memory/grudge-demo.db*`,
restart A, and start again from shot 3. Each full take costs about 6 cents.

---

## 2. Shot list: what to record

Record each shot as its own clip. Let each command finish before cutting.
Shots 5, 6 and 8 must be single continuous clips with no cut inside them.

### Shot 1, the public number (browser + terminal, 15 s)

BaseScan page for the ERC-8004 Reputation Registry
`https://basescan.org/address/0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`, then in window B:

```
node src/erc8004.js score 0x89E9E1ab11dD1B138b1dcE6d6A4a0926aaFD5029
```

Capture: `{ agentId: '1', score: 0.81, count: 39 }`. One number, 39 raters.

### Shot 2, the number is farmable (terminal, 10 s)

```
node src/erc8004.js score 0xd82ac03aba79b88213cec1a78832d85665526036
```

Capture: our own sandbox provider with a public score of 100 from ratings we
wrote ourselves. This is the proof for "farmable at the price of one job".

### Shot 3, empty memory (window A + E, 10 s)

Start window A. Capture the startup line
`[MEMORY] service up ... sibyl tier=... account=activated`. Then window E:
both broker panels say "no warm entities yet", journal empty, log empty.

### Shot 4, session 1: hired on the public number and burned (window B, then A and E, about 2 min of capture, will be cut to 55 s)

Window B:

```
node src/hire.js --tenant broker-a --category research --budget 0.02 --pool pools/demo.json --feedback
```

Capture in order, these are the frames Remotion will hold on:

1. The ranking table: both providers `unknown`, sandbox 1 (public 0.97) on top,
   terms `2x`, `eval yes`, `retry 1`, `cap 0.05`, premium `21%`.
2. The two lines under it:
   `WITHOUT MEMORY: hire 0x39d0..ee6f (top public 0.97), single job, no evaluator, 0 retries`
   `WITH MEMORY: same provider ... stages 1 -> 2, evaluator no -> yes, retries 0 -> 1`.
3. `[CHAIN] BROKER_A tx 0x...` create and fund lines with BaseScan links.
4. `[GRUDGE] evaluated against REFERENCE spec:research: score 0 (0/5), unmet [...]`.
5. `[ACP] job ... job.rejected` and `[GRUDGE] refund check: escrow returned in full`.
6. Stage 2 repeats the miss, then
   `outcome job ...: disputed, score 0, failure=true, status probation (PROMOTED to warm entity)`.
7. `[CHAIN] ERC-8004 giveFeedback(agent 84165, value 0, ...) tx 0x...`.

Window A, capture these three lines as they appear:
`[MEMORY] write tenant=broker-a journal event ...`
`[MEMORY] write tenant=broker-a PROMOTE journal -> entity counterparty/0x39d04d78 after 2 samples / 2 failures, status=probation`
`[MEMORY] write tenant=consortium signal/0x39d04d78 status=probation live_failures=2 reporters=1 (redacted, by broker-a)`

Window E after the run: sandbox 1 row `probation`, spec bar at 0.00, the
failure column naming the job id and time, consortium panel with one signal.

### Shot 5, kill the broker, show the empty terminal (window B, 10 s, one clip)

The broker already exited. Press Ctrl-L or `clear`, then type `history | tail -1`
so the previous hire command is visible as history and nothing else is on
screen. Hold 3 seconds. Say nothing fancy: this is the fresh-session proof.
The memory service in window A stays up.

### Shot 6, session 2: cold start, GRUDGE refuses by name and hires the other one (window B, one continuous clip, no cut, about 1:30 of capture cut to 45 s)

```
node src/hire.js --tenant broker-a --category research --budget 0.02 --pool pools/demo.json --feedback
```

Capture:

1. The ranking table: sandbox 1 now `probation`, verdict `REFUSE`, reason line
   `probation in research: burned us on job <id> on <date>; public score 0.97 ignored`.
   Sandbox 2 `unknown`, `HIRE`.
2. `-> HIRE 0xd82a...` and the counterfactual lines:
   `WITHOUT MEMORY: hire 0x39d0..ee6f (top public 0.97) ...`
   `memory knows this provider as probation with 2 live failures`
   `WITH MEMORY: different provider (0xd82a..6036); ...`
3. Sandbox 2 delivers, `score 1 (5/5)`, `job.completed`, `giveFeedback(agent 84571, value 100`.

DO NOT CUT between the table and the counterfactual lines. That pair is the
load-bearing moment.

### Shot 7, what trust buys (window B, 10 s)

Run one more real session first so sandbox 2 reaches three samples for broker A
(same command as shot 6, it takes a minute, no need to capture it), then:

```
node src/hire.js --tenant broker-a --category research --budget 0.02 --pool pools/demo.json --dry-run
```

Capture: sandbox 2 `trusted`, `staged no`, `eval no`, `retry 2`, premium `0%`,
`cap 0.7125`, and the line `escrow cap 0.02 -> 0.7125 ... evaluator no -> no, retries 0 -> 2`.

### Shot 8, the deletion test, live (window B, one continuous clip, 60 s)

```
cd ~/Developer/grudge && scripts/deletion_test.sh
```

Capture the three PASS lines and the block in phase 2:
`GRUDGE: memory layer is gone. ... There is no fallback path. Exiting with code 3.`
and in phase 3 the hire of `0x2222...` again. Then, still recording, switch to
window A, press Ctrl-C on the memory service, switch to window E: the viewer
flips to `MEMORY LAYER GONE` within two seconds. Restart window A with the same
`--db` path afterwards (memory is on disk, nothing is lost).

### Shot 9, broker B, a different process that never met the provider (window B, 20 s)

```
GRUDGE_TENANT=broker-b node src/hire.js --agent BROKER_B --category research --budget 0.02 --pool pools/demo.json
```

Capture: sandbox 1 `unknown` to broker B yet `REFUSE`, reason starting
`consortium: 2 live failures in ['research'] reported by ['broker-a']`. Window A
shows `[MEMORY] read tenant=consortium signal/0x39d04d78`. Window E shows
broker-b's panel still empty while the consortium panel has the signal.

### Shot 10, BaseScan (browser, 20 s)

Open, in this order, and hold 4 seconds each:
1. The fund transaction from shot 4 (any `[CHAIN] BROKER_A tx` link).
2. The reject transaction from shot 4.
3. The giveFeedback transaction from shot 6, value 100, on agent 84571.
4. `https://basescan.org/address/0x8004BAa17C55a88189AE136b182e5fdA19dE9b63#events`
   showing the NewFeedback events with tag `grudge`.

### Shot 11, repo (browser, 10 s)

`https://github.com/big14way/grudge`: scroll from the title to the session
table in section 2, then to section 11, the memory index with line links.

---

## 3. Narration, word for word (3:00 cut)

About 150 words per minute. 430 words, 2:55 of speech, 3:00 with the cards.
Every scene from the shot list stays; the holds get shorter, not the content.

### Scene 1, problem (0:00 to 0:22) over shots 1 and 2

> Agents hire agents now. On Virtuals ACP a buyer agent picks a provider, funds escrow, and pays, with no human in the loop. It picks by reputation, and reputation is one number. This is ERC-8004 on Base: agent one, score 81, thirty-nine raters, none of them you. Here is a provider we control: score one hundred. We wrote every rating ourselves for a cent a job. The number is farmable, it is nobody's, and a buyer forgets it between sessions anyway.

### Scene 2, product (0:22 to 0:32) over shot 3

> GRUDGE is a buyer agent for ACP with its own private memory of every counterparty, in Sibyl Memory. Who to hire, what terms, what price: all three come from that memory and nothing else. It is built for teams running autonomous buyers that hire many times a day. Memory, empty. Watch it fill.

### Scene 3, session one (0:32 to 1:10) over shot 4

> Session one, two strangers. The public score says hire the first. GRUDGE agrees, on stranger terms: two stages, evaluator required, a ten percent escrow cap, a twenty-one percent premium. Read the two lines: without memory, one job at full budget; with memory, the same provider on a leash.
>
> Funded on Base. The delivery scores zero of five against the stored spec. Rejected, escrow refunded, retry, zero again. On the left: one journal event per job, two failures promote the provider into a warm entity, rewritten in place, status probation. A redacted signal goes to the consortium tenant. And a zero goes on chain to ERC-8004.

### Scene 4, kill and cold start (1:10 to 1:45) over shots 5 and 6

> Kill the broker. Empty terminal. It holds nothing.
>
> Session two, cold start, same candidates, same public scores. GRUDGE refuses the top-rated provider and names the job and the date that burned it. Public score point nine seven, ignored. It hires the second provider instead. The two lines: without memory, the burned provider at flat terms; with memory, a different provider, capped and staged. That is the decision memory changed. Five of five, settled, good rating on chain.

### Scene 5, trust (1:45 to 1:57) over shot 7

> Memory is not only grudges. Three clean deliveries later the second provider is trusted: no staging, no evaluator, two retries, no premium, escrow cap up thirty-five times. Proven providers get cheaper to hire.

### Scene 6, deletion test (1:57 to 2:32) over shot 8

> The judges' test: delete the memory layer. Memory up, the broker refuses the burned provider. Memory stopped: it cannot rank, price, or set terms. No fallback. Exit code three. Database wiped: the grudge is gone and it hires the burner again. Stop the service and the viewer goes dark. Without memory GRUDGE is not weaker. It is nothing.

### Scene 7, consortium (2:32 to 2:45) over shot 9

> A second broker, separate process, separate wallet, never met the provider, private memory empty. It reads the consortium signal, two failures reported by broker A, and refuses. No private data crossed. Cold start, solved.

### Scene 8, on chain and close (2:45 to 3:00) over shots 10 and 11

> All of it is on Base mainnet: the escrow, the rejection, the settlement, the feedback tagged grudge on ERC-8004. ACP runs the jobs, Base holds the money and the signal. MIT repo, every memory call indexed by line. Trust is a vector between two agents, not a number everyone shares. GRUDGE is the missing half.

---

## 4. Captions and title cards

Lower-third captions, one per scene, white on dark, monospace:

| scene | caption |
|-------|---------|
| 1 | Public reputation is one number. Everyone sees the same one. |
| 2 | GRUDGE: private memory decides who, what terms, what price |
| 3 | Session 1 · stranger terms · burned twice · status: probation |
| 4 | Session 2 · cold start · refused by job id and date |
| 5 | Trust earned · no staging · no evaluator · cap x35 |
| 6 | Deletion test · exit 3 · no fallback path |
| 7 | Broker B · never met the provider · refused via consortium |
| 8 | Base mainnet · Virtuals ACP · ERC-8004 · MIT |

Title card at 0:00, 2 seconds: `GRUDGE` and under it `private memory as the hiring engine`.
End card at 2:57, 3 seconds: repo URL, `Sibyl Labs hackathon, September 2026`,
the two partner names, the submission commit hash.

Highlight boxes on these exact strings whenever they are on screen:
`WITHOUT MEMORY` / `WITH MEMORY`, `PROMOTE journal -> entity`,
`REWRITTEN IN PLACE`, `burned us on job`, `Exiting with code 3.`,
`MEMORY LAYER GONE`, `consortium: 2 live failures`.

---

## 5. Remotion assembly order (3:00)

| # | scene | source | duration | notes |
|---|-------|--------|----------|-------|
| 0 | title card | none | 0:02 | |
| 1 | problem | shots 1, 2 | 0:20 | 2 s hold on `score: 0.81, count: 39`, 2 s on the 100 |
| 2 | product | shot 3 | 0:10 | startup line, empty viewer |
| 3 | session 1 | shot 4 | 0:38 | ACP waits at 8x; 2 s holds on the table, the WITHOUT/WITH lines, `0/5`, `PROMOTE`, the consortium line |
| 4 | kill + session 2 | shots 5, 6 | 0:35 | shot 5 trimmed to 3 s; shot 6 UNEDITED from the table through the WITH MEMORY line, then 8x to `5/5` |
| 5 | trust | shot 7 | 0:12 | hold on the trusted row and the cap line |
| 6 | deletion | shot 8 | 0:35 | phase 2 block UNEDITED; other waits 8x; end 2 s on MEMORY LAYER GONE |
| 7 | consortium | shot 9 | 0:13 | hold on the consortium reason |
| 8 | on chain + close | shots 10, 11 | 0:12 | 2 s per BaseScan page, 4 s repo scroll |
| 9 | end card | none | 0:03 | |

Total 3:00. OS clock visible in every captured clip. Speed changes only during
ACP waits (`created` to `budget.set`, `funded` to `submitted`). Never inside
the refusal table, the WITHOUT/WITH lines, or deletion phase 2.

---

## 6. Rules checklist

- [ ] Problem, audience, product, mechanics, Sibyl usage, fresh-session recall: scenes 1, 2, 3, 4.
- [ ] Load-bearing moment unmistakable: scene 4 WITHOUT/WITH lines, scene 6 exit 3.
- [ ] Fresh session recall shown unedited: shot 6.
- [ ] Deletion performed on camera: shot 8.
- [ ] Both partner stacks doing real work on screen: ACP job events, giveFeedback tx.
- [ ] Timestamp on screen: OS clock plus viewer clock.
- [ ] 2 to 5 minutes: 3:00.
- [ ] Posted with @sibylcap, @virtuals_io, @base: docs/POSTS.md.
