/**
 * GRUDGE sandbox provider. Our own ACP seller so no live provider is on the
 * critical path. PROVIDER_MODE=good delivers a spec-meeting brief;
 * PROVIDER_MODE=burn delivers something that misses the spec (the demo's
 * session 1). PROVIDER_MODE=overcharge sets a budget above the offering price.
 *
 *   node src/provider.js [--mode good|burn|overcharge] [--price 0.01] [--agent PROVIDER|PROVIDER2]
 */
import { parseArgs } from "node:util";
import { AssetToken } from "@virtuals-protocol/acp-node-v2";
import { loadEnv } from "./env.js";
import { createAgent } from "./acp.js";
import { log, short } from "./render.js";

loadEnv();
const { values: a } = parseArgs({
  options: {
    mode: { type: "string", default: process.env.PROVIDER_MODE || "good" },
    price: { type: "string", default: process.env.PROVIDER_PRICE || "0.01" },
    agent: { type: "string", default: "PROVIDER" },   // env prefix: PROVIDER or PROVIDER2
  },
});

const GOOD = `# Summary
This research brief covers the requested topic with the depth a decision needs. ${"It reviews the current landscape, the main actors, the technical constraints and the open questions, then ranks the options. ".repeat(8)}
- Source: https://eips.ethereum.org/EIPS/eip-8004
- Source: https://whitepaper.virtuals.io/acp-product-resources/acp-dev-onboarding-guide
- Source: https://docs.base.org
Risks and caveats: the main risk is data staleness; the second limitation is provider self-reporting. Recommendation follows in the conclusion.`;

const BURN = `Here is your report. It is short. Trust me, it is fine.`;

async function main() {
  const { agent, address } = await createAgent(a.agent, { label: a.agent });
  const price = Number(a.price);
  log(a.agent, `wallet ${short(address)} mode ${a.mode} price ${price} USDC. Listening for GRUDGE jobs.`);

  const budgeted = new Set();
  agent.on("entry", async (session, entry) => {
    try {
      if (entry.kind === "message" && entry.contentType === "requirement" && session.status === "open" && !budgeted.has(session.jobId)) {
        budgeted.add(session.jobId);
        const amount = a.mode === "overcharge" ? price * 2 : price;
        log(a.agent, `job ${session.jobId} requirement received (${entry.content.length} chars); setBudget ${amount}`);
        await session.setBudget(AssetToken.usdc(amount, session.chainId));
      }
      if (entry.kind === "system") {
        log(a.agent, `job ${session.jobId} ${entry.event.type}`);
        if (entry.event.type === "job.created" && session.roles.includes("provider")) {
          // Raw jobs may carry no requirement message. Budget after a short grace period.
          setTimeout(async () => {
            if (budgeted.has(session.jobId) || session.status !== "open") return;
            budgeted.add(session.jobId);
            const amount = a.mode === "overcharge" ? price * 2 : price;
            log(a.agent, `job ${session.jobId} no requirement after 20s; setBudget ${amount}`);
            try { await session.setBudget(AssetToken.usdc(amount, session.chainId)); }
            catch (err) { log(a.agent, `setBudget failed: ${err.shortMessage || err.message}`); }
          }, 20_000);
        }
        if (entry.event.type === "job.funded") {
          const text = a.mode === "burn" ? BURN : GOOD;
          await session.submit(text);
          log(a.agent, `job ${session.jobId} submitted ${a.mode === "burn" ? "a spec-missing" : "a spec-meeting"} deliverable (${text.length} chars)`);
        }
      }
    } catch (err) {
      log(a.agent, `error on job ${session.jobId}: ${err.shortMessage || err.message}`);
    }
  });

  await agent.start(() => log(a.agent, "connected to ACP event stream"));
}

main().catch((err) => { console.error(err); process.exit(1); });
