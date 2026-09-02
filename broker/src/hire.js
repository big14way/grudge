/**
 * The buyer path. Memory decides WHO / TERMS / PRICE, ACP executes, memory
 * records the outcome, ERC-8004 gets our public feedback.
 *
 *   node src/hire.js --category research --budget 0.02 [--pool pools/x.json | --browse "research"]
 *                    [--tenant broker-a] [--agent BROKER_A] [--feedback]
 *
 * Flow per ACP job (repeated per stage when terms say staged):
 *   memory.decide -> createJobByOfferingName -> budget.set (check <= max_price) -> fund
 *   -> job.submitted -> memory.evaluate(deliverable) -> complete | reject
 *   -> memory.outcome (journal + trust vector rewrite + consortium signal)
 *   -> optional giveFeedback on Base mainnet with the commitment as feedbackHash
 */
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { AssetToken } from "@virtuals-protocol/acp-node-v2";
import { loadEnv } from "./env.js";
import { Memory, requireMemory } from "./memory.js";
import { chainId, createAgent, fillRequirement } from "./acp.js";
import { publicScore, giveFeedback, resolveAgentId } from "./erc8004.js";
import { log, renderDecision, short } from "./render.js";

loadEnv();
const { values: a } = parseArgs({
  options: {
    tenant: { type: "string", default: process.env.GRUDGE_TENANT || "broker-a" },
    agent: { type: "string", default: process.env.GRUDGE_AGENT || "BROKER_A" },
    category: { type: "string", default: "research" },
    budget: { type: "string", default: "0.02" },
    pool: { type: "string" },
    browse: { type: "string" },
    feedback: { type: "boolean", default: false },
    "dry-run": { type: "boolean", default: false },
    timeout: { type: "string", default: "900" },
  },
});

const memory = new Memory({ tenant: a.tenant });
const CHAIN = chainId();

async function candidatesFromPool(file) {
  const pool = JSON.parse(readFileSync(file, "utf8"));
  return pool.candidates.map((c) => ({ ...c, address: c.address.toLowerCase() }));
}

async function candidatesFromBrowse(agent, keyword) {
  const found = await agent.browseAgents(keyword, { topK: 8, showHidden: true });
  const out = [];
  for (const ag of found) {
    const off = (ag.offerings || []).find((o) => !o.isHidden && Number(o.priceValue) > 0) || ag.offerings?.[0];
    if (!off || !ag.walletAddress) continue;
    let pub = null;
    try { pub = await publicScore(ag.walletAddress); } catch { pub = null; }
    out.push({
      address: ag.walletAddress.toLowerCase(), name: ag.name, offering: off.name, requirements: off.requirements,
      quoted_price_usdc: Number(off.priceValue), sla_minutes: off.slaMinutes,
      public_score: pub?.score ?? (ag.rating != null ? Number(ag.rating) / 5 : null), erc8004: pub,
    });
  }
  return out;
}

function specText(spec, stage, stages) {
  const crit = (spec?.criteria || []).map((c) => `${c.id}: ${c.type} ${JSON.stringify(c.value)}${c.pattern ? ` /${c.pattern}/` : ""}`);
  return `GRUDGE ${a.category} job${stages > 1 ? ` (stage ${stage} of ${stages})` : ""}. Deliver plain text meeting ALL of: ${crit.join("; ")}.`;
}

/** Run one ACP job against `chosen`. Resolves with the outcome recorded in memory. */
function runJob({ agent, address: buyer, adapter }, chosen, spec, stage, stages, terms) {
  return new Promise(async (resolve, reject) => {
    const t0 = Date.now();
    let jobId = null;
    let funded = null;
    let deliverable = null;
    let evaluation = null;
    let done = false;
    const timer = setTimeout(() => { if (!done) { done = true; reject(new Error(`job ${jobId} timed out after ${a.timeout}s`)); } }, Number(a.timeout) * 1000);

    const finish = async (action, extra = {}) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      const latency = (Date.now() - t0) / 1000;
      const score = evaluation?.score ?? (action === "released" ? 1 : 0);
      const outcome = await memory.outcome({
        provider: chosen.address, acp_job_id: Number(jobId), category: a.category, score, action,
        reason: extra.reason || evaluation?.notes || action,
        quoted_price_usdc: chosen.quoted_price_usdc, charged_price_usdc: funded ?? chosen.quoted_price_usdc,
        latency_s: latency, sla_s: spec?.sla_seconds, tx_hash: extra.tx_hash, chain_id: CHAIN,
        broker_wallet: buyer, public_score: chosen.erc8004 || (chosen.public_score != null ? { score: chosen.public_score } : null),
        evaluation, lesson: extra.lesson,
      });
      log("GRUDGE", `outcome job ${jobId}: ${action}, score ${score}, failure=${outcome.failure}, status ${outcome.status}${outcome.promoted ? " (PROMOTED to warm entity)" : ""}`);
      resolve({ jobId, action, score, outcome, evaluation, latency });
    };

    agent.on("entry", async (session, entry) => {
      if (String(session.jobId) !== String(jobId)) return;
      try {
        if (entry.kind === "system") {
          const ev = entry.event;
          log("ACP", `job ${jobId} ${ev.type}${ev.amount != null ? ` amount ${ev.amount}` : ""}${ev.reason ? ` "${ev.reason}"` : ""}`);
          switch (ev.type) {
            case "budget.set": {
              const amount = Number(ev.amount);
              if (amount > chosen.max_price_usdc + 1e-9) {
                log("GRUDGE", `budget ${amount} exceeds our max price ${chosen.max_price_usdc} (private premium ${Math.round(chosen.risk_premium * 100)}%). NOT funding.`);
                await finish("refused", { reason: `price: budget ${amount} > max ${chosen.max_price_usdc}`, lesson: "provider prices above our private risk-adjusted ceiling" });
                return;
              }
              await memory.inflight(Number(jobId), { stage: "budget.set", amount, max_price_usdc: chosen.max_price_usdc, terms });
              await session.fund(AssetToken.usdc(amount, session.chainId));
              funded = amount;
              break;
            }
            case "job.submitted": {
              deliverable = ev.deliverable || session.job?.deliverable || "";
              evaluation = await memory.evaluate(a.category, deliverable);
              log("GRUDGE", `evaluated against REFERENCE spec:${a.category}: score ${evaluation.score} (${evaluation.criteria_met}/${evaluation.criteria_total}), unmet ${JSON.stringify(evaluation.unmet)}`);
              if (session.roles.includes("evaluator")) {
                if (evaluation.score >= 0.5) await session.complete(`GRUDGE: spec met ${evaluation.criteria_met}/${evaluation.criteria_total}`);
                else await session.reject(`GRUDGE: spec unmet: ${evaluation.unmet.join(", ")}`);
              }
              break;
            }
            case "job.completed":
              await finish(evaluation && evaluation.score < 0.5 ? "released-despite-fail" : "released");
              break;
            case "job.rejected":
              await finish("disputed", { reason: `rejected: ${ev.reason}`, lesson: "tighten terms, provider missed spec" });
              break;
            case "job.expired":
              await finish("expired", { reason: "job expired before delivery", lesson: "provider did not deliver inside SLA" });
              break;
          }
        } else if (entry.kind === "message" && entry.contentType === "deliverable" && !deliverable) {
          deliverable = entry.content;
        }
      } catch (err) {
        if (!done) { done = true; clearTimeout(timer); reject(err); }
      }
    });

    const requirement = fillRequirement(chosen.requirements, specText(spec, stage, stages));
    const opts = terms.require_evaluator ? { evaluatorAddress: buyer } : {};
    log("ACP", `createJobByOfferingName chain ${CHAIN} offering "${chosen.offering}" provider ${short(chosen.address)} evaluator ${terms.require_evaluator ? "self" : "none"}`);
    jobId = await agent.createJobByOfferingName(CHAIN, chosen.offering, chosen.address, requirement, opts);
    log("ACP", `job ${jobId} created`);
    await memory.inflight(Number(jobId), { stage: "created", offering: chosen.offering, provider: chosen.address, terms });
  });
}

async function main() {
  await requireMemory(memory);
  log("GRUDGE", `tenant ${a.tenant} agent ${a.agent} chain ${CHAIN} memory ${memory.url}`);

  let acp = null;
  let candidates;
  if (a.browse) {
    acp = await createAgent(a.agent, { label: a.agent });
    await acp.agent.start();
    candidates = await candidatesFromBrowse(acp.agent, a.browse);
    log("ACP", `browseAgents("${a.browse}") -> ${candidates.length} candidates with offerings`);
  } else {
    candidates = await candidatesFromPool(a.pool || "pools/sample.json");
  }
  if (!candidates.length) { log("GRUDGE", "no candidates"); process.exit(4); }

  const spec = (await memory.spec(a.category)).spec;
  const decision = await memory.decide({ category: a.category, budget_usdc: Number(a.budget) }, candidates);
  console.log(renderDecision(decision));
  if (!decision.chosen) { log("GRUDGE", "memory refused every candidate. No job created."); process.exit(5); }
  const chosen = { ...candidates.find((c) => c.address === decision.chosen.address), ...decision.chosen };
  const terms = decision.chosen.terms;
  if (a["dry-run"]) { log("GRUDGE", "dry run, stopping before ACP"); process.exit(0); }

  if (!acp) { acp = await createAgent(a.agent, { label: a.agent }); await acp.agent.start(); }
  const stages = terms.staged ? terms.stages : 1;
  let retries = terms.retry_budget;
  const results = [];
  for (let stage = 1; stage <= stages; stage++) {
    log("GRUDGE", `stage ${stage}/${stages}: terms cap ${terms.max_job_usdc} USDC, evaluator ${terms.require_evaluator ? "required" : "waived"}, retries left ${retries}, dispute window ${terms.dispute_window_s}s`);
    const r = await runJob(acp, chosen, spec, stage, stages, terms);
    results.push(r);
    if (a.feedback && r.outcome) {
      try {
        const agentId = chosen.erc8004?.agentId ?? (await resolveAgentId(chosen.address));
        if (agentId === null || agentId === undefined) log("CHAIN", `no ERC-8004 agentId for ${short(chosen.address)}; skipping giveFeedback`);
        else {
          const hash = await giveFeedback(acp.adapter, { agentId, score: r.score, category: a.category, commitment: r.outcome.commitment || `0x${"0".repeat(64)}` });
          log("CHAIN", `ERC-8004 giveFeedback(agent ${agentId}, value ${Math.round(r.score * 100)}, tag grudge/${a.category}) tx ${hash}`);
        }
      } catch (err) { log("CHAIN", `giveFeedback failed: ${err.shortMessage || err.message}`); }
    }
    if (r.score < 0.5) {
      if (retries > 0) { retries -= 1; log("GRUDGE", `stage ${stage} failed spec; retry budget allows one more attempt`); }
      else { log("GRUDGE", `stage ${stage} failed spec and retry budget is exhausted. Stopping.`); break; }
    }
  }
  const cp = await memory.counterparty(chosen.address);
  log("GRUDGE", `final: ${short(chosen.address)} status ${cp.status}${cp.vector ? ` trust ${JSON.stringify(cp.vector.trust)} failures ${cp.vector.failures.length}` : " (journal only)"}`);
  log("CHAIN", `${acp.txLog.length} transactions: ${acp.txLog.map((t) => t.hash).join(", ") || "none"}`);
  await acp.agent.stop();
  process.exit(results.some((r) => r.score < 0.5) ? 6 : 0);
}

main().catch((err) => { console.error(err); process.exit(1); });
