# Pilot GRUDGE as your hiring layer

GRUDGE is a decision service. Your buyer agent keeps its own ACP code; before
each hire it asks GRUDGE who to hire, on what terms, at what price, and after
each job it tells GRUDGE what happened. Everything else is yours.

## Integration, three HTTP calls

```
POST /decide    { job: {category, budget_usdc}, candidates: [{address, public_score, quoted_price_usdc}] }
                -> ranked candidates, chosen provider, terms, max price, and the memoryless counterfactual
POST /evaluate  { category, delivery }   -> score against your stored acceptance spec
POST /outcome   { provider, acp_job_id, category, score, action, prices, latency, ... }
                -> updates the private trust vector, journal, and the consortium signal
```

Tenant is a header (`X-Grudge-Tenant`), so several of your agents share one
service with isolated memory. Your acceptance specs live in the REFERENCE tier
(`PUT /spec/<category>`), so your own criteria drive the evaluator.

## What you get

- A private trust vector per provider, learned from your own jobs only.
- Refusals that name the job and date that caused them.
- Terms that tighten on strangers and burned providers, and loosen on proven ones.
- A risk premium on price from what you have seen, not from a global average.
- Optional: your evaluator scores published to ERC-8004 with a chain-bound commitment.

## What it costs

Nothing. MIT. One Python process on localhost, one SQLite file under
`~/.sibyl-memory/`. No cloud, no keys leave your machine.

## Pilot terms

Run it beside your existing buyer for a week. Compare the decisions GRUDGE
would have made (`--dry-run` prints them without spending) with what your
buyer did. If it would have saved you a failed job, keep it.

To say yes, or to ask something, comment on the pilot thread:
https://github.com/big14way/grudge/issues/1
