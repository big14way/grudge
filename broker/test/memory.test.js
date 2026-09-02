import test from "node:test";
import assert from "node:assert/strict";
import { Memory, MemoryUnavailableError, requireMemory } from "../src/memory.js";

test("requireMemory exits when the service is unreachable", async () => {
  const m = new Memory({ url: "http://127.0.0.1:1" });
  let code = null;
  const origErr = console.error; console.error = () => {};
  try {
    await assert.rejects(requireMemory(m, { exit: (c) => { code = c; } }), MemoryUnavailableError);
  } finally { console.error = origErr; }
  assert.equal(code, 3);
});

test("Memory has no local ranking method", () => {
  const m = new Memory();
  for (const name of Object.getOwnPropertyNames(Memory.prototype)) {
    assert.ok(!/rank|score|price|terms/i.test(name) || name === "decide", `unexpected local method ${name}`);
  }
});
