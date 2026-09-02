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
  return lines.join("\n");
}
