/** Thin terminal rendering. No framework. */

const pad = (s, n) => String(s ?? "").padEnd(n).slice(0, n);
const num = (x, d = 2) => (x === null || x === undefined ? "-" : Number(x).toFixed(d));
export const short = (a) => (a ? `${a.slice(0, 6)}..${a.slice(-4)}` : "-");

export function stamp() {
  return new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export function log(tag, msg) {
  console.error(`[${stamp()}] [${tag}] ${msg}`);
}

export function renderDecision(d) {
  const lines = [];
  lines.push(`job ${d.job.category} budget ${num(d.job.budget_usdc, 4)} USDC  decided ${d.decided_at}`);
  lines.push(`${pad("provider", 14)} ${pad("public", 7)} ${pad("status", 12)} ${pad("private", 8)} ${pad("premium", 8)} ${pad("maxprice", 9)} ${pad("cap", 8)} ${pad("staged", 7)} ${pad("eval", 5)} ${pad("retry", 5)} verdict`);
  for (const r of d.ranked) {
    const t = r.terms || {};
    lines.push(
      `${pad(short(r.address), 14)} ${pad(num(r.public_score), 7)} ${pad(r.status, 12)} ${pad(num(r.private_score), 8)} ` +
      `${pad(`${Math.round((r.risk_premium || 0) * 100)}%`, 8)} ${pad(num(r.max_price_usdc, 4), 9)} ${pad(num(t.max_job_usdc, 4), 8)} ` +
      `${pad(t.staged === null ? "-" : t.staged ? `${t.stages}x` : "no", 7)} ${pad(t.require_evaluator === null ? "-" : t.require_evaluator ? "yes" : "no", 5)} ` +
      `${pad(t.retry_budget, 5)} ${r.verdict.toUpperCase()}`
    );
    lines.push(`${" ".repeat(15)}${r.reason}`);
  }
  lines.push(d.chosen ? `-> HIRE ${d.chosen.address} (${d.chosen.status}, private ${num(d.chosen.private_score)}, pay <= ${num(d.chosen.max_price_usdc, 4)} USDC)`
                      : "-> NO ACCEPTABLE PROVIDER");
  const c = d.counterfactual;
  if (c) {
    lines.push("");
    lines.push(`   WITHOUT MEMORY: hire ${short(c.address)} (top public ${num(c.public_score)}), single job, no evaluator, 0 retries, escrow ${num(c.max_price_usdc, 4)} USDC`);
    lines.push(`   memory knows this provider as ${c.memory_says}${c.live_failures ? ` with ${c.live_failures} live failure${c.live_failures > 1 ? "s" : ""}` : ""}`);
    if (d.chosen && c.delta) {
      const dl = c.delta;
      lines.push(`   WITH MEMORY:    ${dl.provider_changed ? `different provider (${short(d.chosen.address)})` : "same provider"}; escrow cap ${dl.escrow_cap}, max price ${dl.max_price}, stages ${dl.staged}, evaluator ${dl.evaluator}, retries ${dl.retries}, dispute window ${dl.dispute_window_s}s`);
    } else if (!d.chosen) {
      lines.push(`   WITH MEMORY:    no hire. The memoryless broker would have paid ${short(c.address)} again.`);
    }
  }
  return lines.join("\n");
}
