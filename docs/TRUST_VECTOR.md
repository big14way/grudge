# GRUDGE trust vector schema (v1)

Status: CONFIRMED 2026-09-02. Implemented in `memory-service/grudge_memory/` (trust.py = math, store.py = every read and write).

Everything below lives in the Sibyl Memory layer (`sibyl-memory-client` 0.8.0,
verified against source, not docs). Delete the layer and none of the three
decisions (who, what terms, what price) is computable. That is the design.

## Tenants (one SQLite file, one Python writer)

| tenant        | owner     | contents                                   |
|---------------|-----------|--------------------------------------------|
| `broker-a`    | broker A  | full private trust vectors, full journal   |
| `broker-b`    | broker B  | same, independent                          |
| `consortium`  | shared    | redacted signals only, no prices, no specs |

## WARM tier: `category="counterparty"`, `name=<provider wallet, lowercase 0x>`

```jsonc
{
  "schema_version": 1,

  // Four trust dimensions, each 0.0..1.0, each an EWMA (alpha 0.35) of
  // per-job observations. 0.5 is the neutral prior. All decay toward 0.5
  // on read with a 14-day half-life (see DECAY).
  "trust": {
    "spec_adherence":  0.82,   // evaluator score of delivery vs the REFERENCE spec
    "latency":         0.91,   // 1.0 delivered inside SLA, falls linearly to 0 at 2x SLA
    "refund_behavior": 0.50,   // 1.0 rejected job refunded cleanly, 0.0 refund fought/lost
                               // stays at prior until a rejection has actually happened
    "price_drift":     0.97    // 1 - clamp((charged - quoted) / quoted, 0, 1)
  },

  // Same EWMA as spec_adherence but split by job category. Drives WHO for a
  // given job: a great research provider can be a bad writing provider.
  "per_category_competence": { "research": 0.85, "writing": 0.30 },

  "sample_count": 7,          // total jobs we personally ran with them

  // Failures are stored as facts, not a counter, so a refusal can name the
  // specific job and date. Capped at the last 10. A failure is any job whose
  // evaluator score < 0.5 or which we disputed.
  "failures": [
    { "acp_job_id": 1042, "ts": "2026-09-04T13:02:11Z",
      "category": "research", "reason": "3 of 5 acceptance criteria unmet" }
  ],

  "last_seen":  "2026-09-04T13:02:11Z",
  "decayed_at": "2026-09-04T13:02:11Z",   // when decay was last applied and written back

  // Snapshot of the PUBLIC number at the time we last dealt with them, so the
  // demo can show "public said 0.94, we said no".
  "public_score_at_last_job": { "score": 0.94, "feedback_count": 212,
                                "source": "erc8004:8453", "ts": "..." },

  "promoted_at": "2026-09-03T09:10:00Z",  // when this left the journal-only stage
  "promoted_from": "journal"
}
```

`status` (the Sibyl `status` kwarg on `set_entity`, rewritten in place):

| status        | rule (evaluated on every read, live failures only)     |
|---------------|--------------------------------------------------------|
| `trusted`     | < 2 live failures                                      |
| `probation`   | 2 live failures                                        |
| `blacklisted` | >= 3 live failures                                     |

A failure is *live* while it is younger than 30 days. Expired failures drop
out of the count, which is how a blacklisted counterparty returns to probation
and later to trusted. This is the "time decay on read" the brief asks for.

`archive_entity` is never used for status. It has no restore path in the
client. It is reserved for a provider whose wallet is confirmed abandoned or
compromised, and always with a reason.

## Promotion: journal only, then warm

A counterparty we have never hired has no warm entity. Its samples are journal
events found by `search(<address>, tiers=("journal",))`. Promotion to a warm
entity happens on the first of:

- `sample_count >= 3`, or
- 2 failures at any sample count (a burn is a strong signal, we do not wait).

Until promotion, the decision engine treats it as `unknown` and offers probe
terms only. Every promotion is logged to stdout as `[MEMORY] promote`.

## DECAY (applied on read, written back only if it changed something)

```
days = (now - decayed_at).days
trust[k] = 0.5 + (trust[k] - 0.5) * 0.5 ** (days / 14)      # each dimension
per_category_competence[c] likewise
failures = [f for f in failures if age(f) <= 30 days]
status = derive(failures)
```

## The read path: what memory outputs for a hire decision

Input: candidate list `[{address, public_score, offering, quoted_price_usdc}]`
plus the job `{category, size_usdc, sla_seconds}`.

Per candidate the service computes:

```
private_score = 0.40 * spec_adherence
              + 0.20 * per_category_competence[job.category]  (0.5 if absent)
              + 0.15 * latency
              + 0.15 * refund_behavior
              + 0.10 * price_drift
risk_premium  = clamp((0.65 - private_score) * 1.4 + max_observed_price_drift, 0.0, 0.5)
max_price     = job.budget_usdc * (1 - risk_premium)      # what we will pay THIS provider
```

`max_observed_price_drift` comes from a cross-tier `search(<address>)` over the
journal: if they ever charged more than they quoted, the premium remembers it.
The same search widens the dispute window 4x when there is any failure,
dispute or overcharge inside the failure TTL.

Terms by status:

| status      | job size cap        | staged | evaluator | retry budget |
|-------------|---------------------|--------|-----------|--------------|
| trusted     | base * (0.5+score)  | score < 0.80 | score < 0.85 | 2   |
| unknown     | 10% of base         | yes    | required  | 1            |
| probation   | 25% of base         | yes    | required  | 0            |
| blacklisted | REFUSE              | -      | -         | -            |

Refusals, checked in this order:

1. `blacklisted`: refused for everything.
2. `probation` with a live failure in the job's category: refused, and the
   reason names the specific `acp_job_id` and `ts`. Probation providers are
   still hireable in other categories at probation terms.
3. `unknown` to us but the consortium shows >= 2 live failures from other
   brokers: refused, we will not be the next victim.
4. `quoted_price > max_price`: refused on price.
5. `quoted_price > max_job_usdc`: refused on size.

Ranking: hires first, then by status (trusted, unknown, probation), then by
`private_score`, then by public score as the last tie-break among strangers.

Without the memory service none of `private_score`, `risk_premium`, `max_price`
or the terms row is computable. The broker has no fallback formula; it exits.

## COLD tier: one journal event per job, fixed kwargs mapped deliberately

| kwarg       | meaning in GRUDGE                                             |
|-------------|---------------------------------------------------------------|
| `evaluated` | our judgement of the delivery against the REFERENCE spec: `{score, criteria_met, criteria_total, notes}` |
| `acted`     | `{action: hired/refused/disputed/released, provider, why}`     |
| `forward`   | the lesson: what this changes next time, e.g. `{lesson, terms_delta}` |
| `extra`     | structured record: `{acp_job_id, provider, category, quoted_price_usdc, charged_price_usdc, latency_s, sla_s, tx_hash, chain_id}` |

`extra.provider` is what makes `search(<address>, tiers=("journal",))` work.

## HOT tier: state keys

- `negotiation:<acp_job_id>`  live memo state machine position and our budget
- `inflight`                  list of job ids currently escrowed

Nothing else goes in HOT. Cleared when the job resolves.

## REFERENCE tier: spec templates

- `spec:<category>`  `{criteria: [...], sla_seconds, base_size_usdc}`
  Read by the evaluator so the same spec is judged the same way every session.
  Note: `get_reference` returns the body as a JSON string; the service decodes it.

## Consortium signal (tenant `consortium`, `category="signal"`, `name=<address>`)

Redacted. No prices, no job ids, no spec text, no evaluator notes.

```jsonc
{
  "status": "probation",
  "live_failures": 2,
  "last_failure_ts": "2026-09-04T13:02:11Z",
  "categories_failed": ["research"],
  "reporters": 1,
  "commitment": "0x..."   // keccak256(chainid, reputation_registry, broker_wallet, acp_job_id, verdict)
}
```

The commitment lets a broker later prove a specific report was theirs without
the consortium ever holding the private detail. The preimage includes
`chainid` and the registry address so it cannot be replayed across chains or
deployments (the omission Clawback made).

## Decisions confirmed 2026-09-02

1. EWMA alpha 0.35, decay half-life 14 days, failure TTL 30 days, promote at
   3 samples or 2 failures. Confirmed.
2. Demo session 1 reaches probation honestly: an unknown provider gets STAGED
   terms from the terms engine, each stage is evaluated separately, both miss.
   Two spec failures, one job. Confirmed.
3. The risk premium shrinks both the max price we pay and the job size we
   escrow. A fixed-price offering above max price is refused on price. Confirmed.
