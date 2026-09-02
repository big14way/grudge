/**
 * The broker's only door into memory. Every call goes to the Python memory
 * service over localhost HTTP. There is deliberately NO local fallback: no
 * cached ranking, no default terms, no flat price. If the service is not
 * there, requireMemory() exits the process. scripts/deletion_test.sh proves it.
 */

export class MemoryUnavailableError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = "MemoryUnavailableError";
    this.cause = cause;
  }
}

export class Memory {
  constructor({ url = process.env.GRUDGE_MEMORY_URL || "http://127.0.0.1:7411", tenant = "broker-a" } = {}) {
    this.url = url.replace(/\/$/, "");
    this.tenant = tenant;
  }

  async call(method, path, body) {
    let res;
    try {
      res = await fetch(this.url + path, {
        method,
        headers: { "content-type": "application/json", "x-grudge-tenant": this.tenant },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (err) {
      throw new MemoryUnavailableError(`memory service unreachable at ${this.url}`, err);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(`memory ${method} ${path} -> ${res.status}: ${data.error || "error"}`);
    return data;
  }

  health() { return this.call("GET", "/health"); }
  stats() { return this.call("GET", "/stats"); }
  /** WHO / WHAT TERMS / WHAT PRICE. The only ranking code GRUDGE has. */
  decide(job, candidates) { return this.call("POST", "/decide", { job, candidates }); }
  evaluate(category, delivery) { return this.call("POST", "/evaluate", { category, delivery }); }
  outcome(o) { return this.call("POST", "/outcome", o); }
  inflight(acp_job_id, negotiation) { return this.call("POST", "/inflight", { acp_job_id, negotiation }); }
  counterparty(address) { return this.call("GET", `/counterparty/${address}`); }
  counterparties(status) { return this.call("GET", `/counterparties${status ? `?status=${status}` : ""}`); }
  consortium(address) { return this.call("GET", `/consortium/${address}`); }
  journal(address) { return this.call("GET", `/journal/${address}`); }
  spec(category) { return this.call("GET", `/spec/${category}`); }
  multi(query, limit = 10) { return this.call("POST", "/query/multi", { query, limit }); }
}

/** Hard gate. Called at broker startup and before every decision. */
export async function requireMemory(memory, { exit = process.exit } = {}) {
  try {
    const h = await memory.health();
    return h;
  } catch (err) {
    const why = err instanceof MemoryUnavailableError ? err.message : `memory unhealthy: ${err.message}`;
    console.error("");
    console.error("GRUDGE: memory layer is gone.");
    console.error(`  ${why}`);
    console.error("  Cannot rank counterparties, cannot set terms, cannot price risk.");
    console.error("  There is no fallback path. Exiting with code 3.");
    console.error("");
    exit(3);
    throw err; // only reached when exit is stubbed in tests
  }
}
