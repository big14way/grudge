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
import { erc20Abi } from "viem";
import { publicClient, publicScore, giveFeedback, resolveAgentId } from "./erc8004.js";
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
    erc8004: { type: "boolean", default: false },
    only: { type: "string" },          // restrict the pool to one provider address
    task: { type: "string" },          // natural-language task for live providers (default: the spec criteria)
    timeout: { type: "string", default: "900" },
  },
});

const memory = new Memory({ tenant: a.tenant });
const CHAIN = chainId();

async function candidatesFromPool(file) {
  const pool = JSON.parse(readFileSync(file, "utf8"));
  const out = [];
  for (const c of pool.candidates) {
    const cand = { ...c, address: c.address.toLowerCase() };
    if (cand.public_score == null && a.erc8004) {
      try { cand.erc8004 = await publicScore(cand.address); cand.public_score = cand.erc8004.score; } catch { /* stays null */ }
    }
    out.push(cand);
  }
  return out;
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
  if (a.task) return `${a.task}${stages > 1 ? ` (stage ${stage} of ${stages})` : ""}`;
  const crit = (spec?.criteria || []).map((c) => `${c.id}: ${c.type} ${JSON.stringify(c.value)}${c.pattern ? ` /${c.pattern}/` : ""}`);
  return `GRUDGE ${a.category} job${stages > 1 ? ` (stage ${stage} of ${stages})` : ""}. Deliver plain text meeting ALL of: ${crit.join("; ")}.`;
}

const USDC = { 8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" }[CHAIN];
async function usdcBalance(address) {
  const raw = await publicClient().readContract({ address: USDC, abi: erc20Abi, functionName: "balanceOf", args: [address] });
  return Number(raw) / 1e6;
}

/** ACP stores reasons as bytes32; short strings are readable, long ones are hashes. */
function decodeReason(r) {
  if (typeof r !== "string" || !r.startsWith("0x")) return r;
  try {
    const txt = Buffer.from(r.slice(2), "hex").toString("utf8").replace(/\0+$/g, "");
    return /^[\x20-\x7e]+$/.test(txt) ? txt : r.slice(0, 18) + "..";
  } catch { return r; }
}

async function waitForSession(agent, jobId, tries = 30) {
  for (let i = 0; i < tries; i++) {
    const s = agent.getSession(CHAIN, jobId) || agent.getSession(CHAIN, String(jobId));
    if (s) return s;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`no session for job ${jobId}`);
}

/** Run one ACP job against `chosen`. Resolves with the outcome recorded in memory. */
function runJob({ agent, address: buyer, adapter }, chosen, spec, stage, stages, terms) {
  return new Promise(async (resolve, reject) => {
    const t0 = Date.now();
    let jobId = null;
    let funded = null;
    let deliverable = null;
    let evaluation = null;
    let balanceBeforeFund = null;
    let done = false;
    // Wait at least the spec SLA: silence inside the SLA is not yet a fault, silence past it is.
    const waitS = Math.max(Number(a.timeout), Number(spec?.sla_seconds || 0));
    const timer = setTimeout(async () => {
      if (done) return;
      log("GRUDGE", `job ${jobId}: no delivery after ${waitS}s (SLA ${spec?.sla_seconds}s). Recording a no-show.`);
      try { await finish("unresponsive", { reason: `no response within ${waitS}s`, lesson: "provider did not respond inside the SLA; treat silence as a failure" }); }
      catch (err) { done = true; reject(err); }
    }, waitS * 1000);

    const finish = async (action, extra = {}) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      const latency = (Date.now() - t0) / 1000;
      const score = evaluation?.score ?? (action === "released" ? 1 : ["unresponsive", "expired", "refused"].includes(action) ? null : 0);
      const outcome = await memory.outcome({
        provider: chosen.address, acp_job_id: Number(jobId), category: a.category, score, action,
        reason: extra.reason || evaluation?.notes || action,
        quoted_price_usdc: chosen.quoted_price_usdc, charged_price_usdc: funded ?? chosen.quoted_price_usdc,
        latency_s: latency, sla_s: spec?.sla_seconds, tx_hash: extra.tx_hash, chain_id: CHAIN, refunded: extra.refunded ?? null,
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
          log("ACP", `job ${jobId} ${ev.type}${ev.amount != null ? ` amount ${ev.amount}` : ""}${ev.reason ? ` "${decodeReason(ev.reason)}"` : ""}`);
          switch (ev.type) {
            case "budget.set": {
              const amount = Number(ev.amount);
              if (amount > chosen.max_price_usdc + 1e-9) {
                log("GRUDGE", `budget ${amount} exceeds our max price ${chosen.max_price_usdc} (quoted ${chosen.quoted_price_usdc}, private premium ${Math.round(chosen.risk_premium * 100)}%). NOT funding.`);
                // Nothing was delivered, so this is a price observation only: no spec score, no public feedback.
                funded = amount;
                await finish("refused", { reason: `price: budget ${amount} > max ${chosen.max_price_usdc} (quoted ${chosen.quoted_price_usdc})`, lesson: "provider set a budget above its quote; premium rises via price_drift" });
                return;
              }
              await memory.inflight(Number(jobId), { stage: "budget.set", amount, max_price_usdc: chosen.max_price_usdc, terms });
              balanceBeforeFund = await usdcBalance(buyer).catch(() => null);
              await session.fund(AssetToken.usdc(amount, session.chainId));
              funded = amount;
              break;
            }
            case "job.submitted": {
              deliverable = ev.deliverable || session.job?.deliverable || "";
              evaluation = await memory.evaluate(a.category, deliverable);
              evaluation.sample = String(deliverable).slice(0, 400);
              log("GRUDGE", `evaluated against REFERENCE spec:${a.category}: score ${evaluation.score} (${evaluation.criteria_met}/${evaluation.criteria_total}), unmet ${JSON.stringify(evaluation.unmet)}`);
              if (session.roles.includes("evaluator")) {
                if (evaluation.score >= 0.5) await session.complete(`GRUDGE: spec met ${evaluation.criteria_met}/${evaluation.criteria_total}`);
                else await session.reject(`GRUDGE: spec unmet: ${evaluation.unmet.join(", ")}`);
              }
              break;
            }
            case "job.completed":
              await finish(evaluation && evaluation.score < 0.5 ? "released-despite-fail" : "released", { reason: decodeReason(ev.reason) });
              break;
            case "job.rejected": {
              // Did the escrow come back? Observed, not assumed: compare the buyer's USDC balance.
              let refunded = null;
              if (balanceBeforeFund !== null) {
                for (let i = 0; i < 6 && refunded !== true; i++) {
                  const now = await usdcBalance(buyer).catch(() => null);
                  if (now !== null && now >= balanceBeforeFund - 1e-9) refunded = true;
                  else { refunded = false; await new Promise((r) => setTimeout(r, 5000)); }
                }
                log("GRUDGE", `refund check: ${refunded ? "escrow returned in full" : "escrow NOT returned"} (before ${balanceBeforeFund}, now ${await usdcBalance(buyer).catch(() => "?")})`);
              }
              await finish("disputed", { reason: `spec unmet: ${(evaluation?.unmet || []).join(", ") || decodeReason(ev.reason)}`, refunded, lesson: "tighten terms, provider missed spec" });
              break;
            }
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

    const text = specText(spec, stage, stages);
    const opts = terms.require_evaluator ? { evaluatorAddress: buyer } : {};
    if (chosen.offering) {
      const requirement = fillRequirement(chosen.requirements, text, { address: buyer });
      log("ACP", `requirement ${JSON.stringify(requirement).slice(0, 160)}`);
      log("ACP", `createJobByOfferingName chain ${CHAIN} offering "${chosen.offering}" provider ${short(chosen.address)} evaluator ${terms.require_evaluator ? "self" : "none"}`);
      jobId = await agent.createJobByOfferingName(CHAIN, chosen.offering, chosen.address, requirement, opts);
      log("ACP", `job ${jobId} created`);
    } else {
      // No registered offering: raw ACP job, then the requirement as the first message.
      const sla = Number(spec?.sla_seconds || 900);
      log("ACP", `createJob chain ${CHAIN} provider ${short(chosen.address)} evaluator ${terms.require_evaluator ? "self" : "none"} expires in ${sla}s`);
      jobId = await agent.createJob(CHAIN, { providerAddress: chosen.address, evaluatorAddress: terms.require_evaluator ? buyer : undefined, expiredAt: Math.floor(Date.now() / 1000) + sla, description: `GRUDGE ${a.category}` });
      log("ACP", `job ${jobId} created; sending requirement`);
      const session = await waitForSession(agent, jobId);
      await session.sendMessage(text, "requirement");
    }
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
  if (a.only) candidates = candidates.filter((c) => c.address === a.only.toLowerCase());
  if (!candidates.length) { log("GRUDGE", "no candidates"); process.exit(4); }

  // One multi-record question per session, answered across linked journal records (two Sibyl stages + exact).
  const q = `${a.category} specfail overcharged`;
  const mr = await memory.multi(q);
  log("MEMORY", `multi-record "${q}": ${mr.verdict}, ${mr.hits.length} admitted by Sibyl retrieve+verify, ${mr.exact.length} exact -> ${mr.providers.length ? mr.providers.map(short).join(", ") : "nobody"} failed ${a.category} AND overcharged`);

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
    if (a.feedback && r.outcome && r.score !== null) {   // only publish a judgement when there was a delivery to judge
      try {
        const agentId = chosen.erc8004?.agentId ?? (await resolveAgentId(chosen.address));
        if (agentId === null || agentId === undefined) log("CHAIN", `no ERC-8004 agentId for ${short(chosen.address)}; skipping giveFeedback`);
        else {
          const hash = await giveFeedback(acp.adapter, { agentId, score: r.score, category: a.category, commitment: r.outcome.commitment || `0x${"0".repeat(64)}` });
          log("CHAIN", `ERC-8004 giveFeedback(agent ${agentId}, value ${Math.round(r.score * 100)}, tag grudge/${a.category}) tx ${hash}`);
        }
      } catch (err) { log("CHAIN", `giveFeedback failed: ${err.shortMessage || err.message}`); }
    }
    if (r.action === "refused") { log("GRUDGE", "price refusal: not retrying the same provider"); break; }
    if (r.score === null || r.score < 0.5) {
      if (retries > 0) { retries -= 1; log("GRUDGE", `stage ${stage} failed spec; retry budget allows one more attempt`); }
      else { log("GRUDGE", `stage ${stage} failed spec and retry budget is exhausted. Stopping.`); break; }
    }
  }
  const cp = await memory.counterparty(chosen.address);
  log("GRUDGE", `final: ${short(chosen.address)} status ${cp.status}${cp.vector ? ` trust ${JSON.stringify(cp.vector.trust)} failures ${cp.vector.failures.length}` : " (journal only)"}`);
  log("CHAIN", `${acp.txLog.length} transactions: ${acp.txLog.map((t) => t.hash).join(", ") || "none"}`);
  await acp.agent.stop();
  process.exit(results.some((r) => r.score === null || r.score < 0.5) ? 6 : 0);
}

main().catch((err) => { console.error(err); process.exit(1); });
