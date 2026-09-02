#!/usr/bin/env node
/**
 * grudge CLI.
 *   decide   --category research --budget 0.02 --pool pools/sample.json [--tenant broker-a] [--json]
 *   simulate --provider 0x.. --job 1 --score 0.2 [--category research]   (test helper: records an outcome without ACP)
 *   show     --provider 0x..                                              (private vector + consortium signal)
 *   multi    --query "research specfail overcharged"
 */
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { Memory, requireMemory } from "./memory.js";
import { log, renderDecision, short } from "./render.js";

const { positionals, values: a } = parseArgs({
  allowPositionals: true,
  options: {
    tenant: { type: "string", default: process.env.GRUDGE_TENANT || "broker-a" },
    category: { type: "string", default: "research" },
    budget: { type: "string", default: "0.02" },
    pool: { type: "string", default: "pools/sample.json" },
    provider: { type: "string" },
    job: { type: "string" },
    score: { type: "string" },
    query: { type: "string" },
    json: { type: "boolean", default: false },
  },
});

const cmd = positionals[0];
const memory = new Memory({ tenant: a.tenant });

async function main() {
  await requireMemory(memory);
  log("GRUDGE", `tenant ${a.tenant}, memory ${memory.url}`);

  if (cmd === "decide") {
    const pool = JSON.parse(readFileSync(new URL(a.pool, `file://${process.cwd()}/`), "utf8"));
    const job = { category: a.category, budget_usdc: Number(a.budget) };
    const d = await memory.decide(job, pool.candidates);
    if (a.json) { console.log(JSON.stringify(d)); return; }
    console.log(renderDecision(d));
    return;
  }
  if (cmd === "simulate") {
    const score = Number(a.score);
    const r = await memory.outcome({
      provider: a.provider, acp_job_id: Number(a.job), category: a.category, score,
      action: score < 0.5 ? "disputed" : "released", reason: score < 0.5 ? "spec unmet (simulated)" : "ok (simulated)",
      quoted_price_usdc: 0.01, charged_price_usdc: 0.01, latency_s: 120, sla_s: 900,
    });
    log("GRUDGE", `outcome recorded for ${short(a.provider)} job ${a.job}: failure=${r.failure} promoted=${r.promoted} status=${r.status}`);
    if (a.json) console.log(JSON.stringify(r));
    return;
  }
  if (cmd === "show") {
    const cp = await memory.counterparty(a.provider);
    const sig = await memory.consortium(a.provider);
    console.log(JSON.stringify({ private: cp, consortium: sig.signal }, null, 2));
    return;
  }
  if (cmd === "multi") {
    const r = await memory.multi(a.query);
    log("GRUDGE", `multi-record "${a.query}": verdict ${r.verdict}, ${r.hits.length} admitted by Sibyl, ${r.exact.length} exact -> providers ${JSON.stringify(r.providers)}`);
    if (a.json) console.log(JSON.stringify(r));
    return;
  }
  console.error("usage: node src/cli.js <decide|simulate|show|multi> [options]");
  process.exit(2);
}

main().catch((err) => { console.error(err); process.exit(1); });
