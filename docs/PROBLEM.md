# The problem GRUDGE solves

## Setting

Agent-to-agent commerce is not a thought experiment any more. On Virtuals ACP
a buyer agent browses provider agents, picks one, funds an escrow, receives a
deliverable and releases payment, all without a human. Offerings start at
$0.01 and providers are ranked by successful job count and success rate.
ERC-8004 adds an onchain identity and reputation registry for agents on Base,
with tens of thousands of registered agents already.

Every buyer agent today makes its hiring decision from the same input: the
provider's public aggregate score.

## Why the public score is the wrong input for a buyer

**1. It is everyone's, so it is nobody's.** An aggregate is an average of
strangers' opinions about jobs you did not commission. Your own outcome moves
it by one vote. We ran this: our test provider missed our acceptance spec on
three consecutive jobs, was rejected three times, and its public standing was
untouched from the point of view of any other buyer.

**2. It is farmable at the price of one cheap job.** Feedback is written by
whoever paid for a job. We registered a provider on ERC-8004 (agent 84165),
hired it twice for $0.01 from a wallet we control, and it had a public score
of 100 with two ratings. A wash-trade costs cents and the registry cannot tell
a customer from a sock puppet. Notably, the ERC-8004 authors know this: the
deployed `getSummary` reverts unless you pass the list of client addresses
whose feedback you trust. The registry itself refuses to be a universal
scalar. Buyer agents flatten it into one anyway because they have nothing
else.

**3. It is one dimension.** Real counterparties fail in specific ways. One
delivers on spec but charges more than quoted. One is fast but fights refunds.
One is excellent at research and useless at writing. A single score cannot
express "hire them for research, small jobs only, with an evaluator, and never
for writing". A buyer that cannot express that cannot act on it.

**4. The buyer forgets.** Agents are stateless between sessions. Even the
little a buyer did learn is gone on restart. It rehires the same provider at
the same flat terms and loses the same money again. Each loss is a cent, so
no alarm fires. An autonomous buyer running thousands of jobs bleeds steadily
on repeat failures with no human in the loop to notice a pattern.

## What a buyer actually needs

The buyer needs its own answer to three questions, before every job:

- **Who.** Of the candidates, which one has earned my trust, in this
  category, recently, from jobs I ran?
- **What terms.** How much do I risk on them per job? Do I split the work into
  stages? Do I require an evaluator? How many retries before I stop?
- **What price.** Given what I have seen of their spec adherence, latency,
  refund behaviour and price drift, what premium do I need against the risk?

None of the three can be computed from an aggregate score. All three fall out
of a private, per-counterparty record of past outcomes.

## GRUDGE

GRUDGE is a buyer agent whose private memory is that record and the engine
that turns it into the three answers.

- **Private trust vector per counterparty** in Sibyl Memory: spec adherence,
  latency, refund behaviour, price drift, plus competence per job category.
  Learned only from jobs GRUDGE ran itself. Rewritten in place after every
  job. Decays toward neutral when nothing new is learned, so a grudge fades
  unless it is renewed.
- **Status derived from live failures.** Two spec failures inside 30 days put
  a provider on probation in the category it failed. Three blacklist it
  everywhere. Failures expire, so redemption is possible.
- **Terms and price from the vector**, not from a policy table someone typed:
  job size cap, staging, evaluator requirement, retry budget, dispute window,
  and a risk premium that shrinks what GRUDGE is willing to pay.
- **A consortium tenant** carries a redacted signal between brokers: status,
  failure timestamps, categories, no prices, no job ids, no spec text. A
  broker that has never met a provider still refuses one that burned a peer,
  which solves the cold-start problem without leaking private data.
- **Public write-back.** After each job GRUDGE publishes its evaluator score to
  ERC-8004 with a chain-bound commitment as the feedback hash. The public
  number gains one honest, verifiable vote. Private memory in, public signal
  out.

## Why memory is the product, not a feature

Every one of the three decisions is a function of remembered outcomes. There
is no default formula that produces a decision from the public score alone,
on purpose. Stop the memory service and the broker exits with code 3. Wipe the
database and the broker hires the provider that burned it, at stranger terms,
because the grudge lived only in memory. `scripts/deletion_test.sh` performs
both, live. That is the whole point: a buyer agent without memory is a buyer
agent that can be farmed.
