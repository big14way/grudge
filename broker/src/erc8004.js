/**
 * ERC-8004 on Base mainnet (verified live 2026-09-02: both registries are
 * ERC-1967 proxies; the reputation implementation exposes giveFeedback,
 * getSummary, getClients, readAllFeedback; getSummary reverts on an empty
 * clientAddresses list, so reads go getClients -> getSummary).
 *
 * Read:  publicScore(wallet)  -> the one number every buyer shares
 * Write: giveFeedback(...)    -> our private judgement, published, with the
 *        memory commitment hash as feedbackHash (chainid + registry bound).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createPublicClient, createWalletClient, encodeFunctionData, http, parseAbi } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";
import { log } from "./render.js";
import { loadEnv } from "./env.js";

loadEnv();   // module-level: IDENTITY/REPUTATION/overrides below read process.env, and `node src/erc8004.js` runs standalone

export const IDENTITY = (process.env.ERC8004_IDENTITY_REGISTRY || "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432");
export const REPUTATION = (process.env.ERC8004_REPUTATION_REGISTRY || "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63");

export const reputationAbi = parseAbi([
  "function giveFeedback(uint256 agentId, int128 value, uint8 valueDecimals, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)",
  "function getSummary(uint256 agentId, address[] clientAddresses, string tag1, string tag2) view returns (uint64 count, int128 summaryValue, uint8 summaryValueDecimals)",
  "function getClients(uint256 agentId) view returns (address[])",
  "function getLastIndex(uint256 agentId, address clientAddress) view returns (uint64)",
  "function getIdentityRegistry() view returns (address)",
]);
export const identityAbi = parseAbi([
  "function ownerOf(uint256 tokenId) view returns (address)",
  "function tokenURI(uint256 tokenId) view returns (string)",
  "function register(string agentURI) returns (uint256 agentId)",
]);

export function publicClient() {
  return createPublicClient({ chain: base, transport: http(process.env.BASE_RPC_URL || "https://base-rpc.publicnode.com") });
}

function overrides() {
  const out = {};
  for (const pair of (process.env.ERC8004_AGENT_IDS || "").split(",")) {
    const [w, id] = pair.split("=").map((s) => s?.trim());
    if (w && id) out[w.toLowerCase()] = BigInt(id);
  }
  return out;
}

const CACHE = new URL("../.cache/erc8004-owners.json", import.meta.url);
let ownerIndex = null;   // Map agentId(bigint) -> owner (lowercase), built once per process, cached on disk

function loadCache() {
  try {
    const raw = JSON.parse(readFileSync(CACHE, "utf8"));
    return { max: BigInt(raw.max || 0), owners: new Map(Object.entries(raw.owners || {}).map(([k, v]) => [BigInt(k), v])) };
  } catch { return { max: 0n, owners: new Map() }; }
}

function saveCache(max, owners) {
  mkdirSync(dirname(fileURLToPath(CACHE)), { recursive: true });
  writeFileSync(CACHE, JSON.stringify({ max: max.toString(), builtAt: new Date().toISOString(), owners: Object.fromEntries([...owners].map(([k, v]) => [k.toString(), v])) }));
}

async function ownersChunk(client, from, size) {
  const ids = [];
  for (let id = from; id < from + size; id++) ids.push(id);
  const res = await client.multicall({ contracts: ids.map((id) => ({ address: IDENTITY, abi: identityAbi, functionName: "ownerOf", args: [id] })), allowFailure: true });
  const out = [];
  res.forEach((r, i) => { if (r.status === "success") out.push([ids[i], String(r.result).toLowerCase()]); });
  return out;
}

/**
 * agentId -> owner for every identity NFT. Public RPCs reject wide log scans,
 * so this reads ownerOf via multicall, 1000 ids per call, 4 calls in flight,
 * and caches to broker/.cache. ~90 s on first build for ~84k agents, then
 * incremental. Never called implicitly: run `node src/erc8004.js index`.
 */
export async function buildOwnerIndex(client = publicClient(), { refresh = false } = {}) {
  if (ownerIndex && !refresh) return ownerIndex;
  const { max, owners } = loadCache();
  if (!refresh) { ownerIndex = owners; return owners; }
  const SIZE = 1000n, PAR = 4;
  let from = max + 1n, done = false, calls = 0;
  const t = Date.now();
  while (!done) {
    const batch = [];
    for (let i = 0; i < PAR; i++) batch.push(ownersChunk(client, from + BigInt(i) * SIZE, SIZE));
    const results = await Promise.all(batch);
    calls += PAR;
    for (const rows of results) for (const [id, owner] of rows) owners.set(id, owner);
    done = results.some((r) => r.length === 0);   // a fully empty 1000-id chunk means we passed the end
    from += SIZE * BigInt(PAR);
    if (calls % 20 === 0) log("CHAIN", `ERC-8004 index: ${owners.size} agents so far (${Math.round((Date.now() - t) / 1000)} s)`);
  }
  const newMax = owners.size ? [...owners.keys()].reduce((a, b) => (a > b ? a : b)) : 0n;
  saveCache(newMax, owners);
  ownerIndex = owners;
  log("CHAIN", `ERC-8004 identity index: ${owners.size} agents up to id ${newMax} (${Math.round((Date.now() - t) / 1000)} s, cached)`);
  return owners;
}

/** wallet -> ERC-8004 agentId. Env override first, then the newest identity NFT owned by that wallet in the cached index. */
export async function resolveAgentId(wallet, client = publicClient()) {
  const w = wallet.toLowerCase();
  const ov = overrides()[w];
  if (ov !== undefined) return ov;
  const index = await buildOwnerIndex(client);
  if (!index.size) log("CHAIN", "ERC-8004 owner index empty: run `node src/erc8004.js index` or set ERC8004_AGENT_IDS");
  let found = null;
  for (const [id, owner] of index) if (owner === w) found = id;
  return found;
}

/** The public number: count and mean of all feedback on the agent. Null when not registered. */
export async function publicScore(wallet, client = publicClient()) {
  const agentId = await resolveAgentId(wallet, client);
  if (agentId === null) return { agentId: null, score: null, count: 0, source: "erc8004:8453" };
  const clients = await client.readContract({ address: REPUTATION, abi: reputationAbi, functionName: "getClients", args: [agentId] });
  if (!clients.length) return { agentId: agentId.toString(), score: null, count: 0, source: "erc8004:8453" };
  const [count, value, decimals] = await client.readContract({
    address: REPUTATION, abi: reputationAbi, functionName: "getSummary", args: [agentId, clients, "", ""],
  });
  let score = Number(value) / 10 ** Number(decimals);
  if (score > 1) score = score / 100;        // 0..100 convention -> 0..1
  return { agentId: agentId.toString(), score: Math.max(0, Math.min(1, score)), count: Number(count), source: "erc8004:8453" };
}

/**
 * Publish our judgement. value = evaluator score 0..100 (decimals 0),
 * tag1 = "grudge", tag2 = job category, feedbackHash = the memory
 * commitment keccak256(chainid, registry, broker, jobId, verdict).
 */
export async function giveFeedback(adapter, { agentId, score, category, commitment, feedbackURI = "" }) {
  const value = BigInt(Math.round(Math.max(0, Math.min(1, score)) * 100));
  const args = [BigInt(agentId), value, 0, "grudge", category, "", feedbackURI, commitment];
  if (process.env.FEEDBACK_PRIVATE_KEY && process.env.FEEDBACK_PRIVATE_KEY.length > 10) {
    // Plain EOA path. The Virtuals-sponsored smart wallet only calls allowlisted ACP
    // contracts, so the ERC-8004 registry write goes out from the broker's own key.
    const account = privateKeyToAccount(process.env.FEEDBACK_PRIVATE_KEY);
    const wallet = createWalletClient({ account, chain: base, transport: http(process.env.BASE_RPC_URL || "https://base-rpc.publicnode.com") });
    const hash = await wallet.writeContract({ address: REPUTATION, abi: reputationAbi, functionName: "giveFeedback", args });
    log("CHAIN", `FEEDBACK EOA ${account.address} tx ${hash}  https://basescan.org/tx/${hash}`);
    return hash;
  }
  const data = encodeFunctionData({ abi: reputationAbi, functionName: "giveFeedback", args });
  const res = await adapter.sendCalls(base.id, [{ to: REPUTATION, data, value: 0n }]);
  return [].concat(res)[0];
}

// CLI: node src/erc8004.js index | score <wallet>
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [cmd, arg] = process.argv.slice(2);
  if (cmd === "index") await buildOwnerIndex(publicClient(), { refresh: true });
  else if (cmd === "score" && arg) console.log(await publicScore(arg));
  else console.error("usage: node src/erc8004.js index | score <wallet>");
}
