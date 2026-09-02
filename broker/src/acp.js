/**
 * Virtuals ACP v2 wiring. One function builds an AcpAgent for a wallet prefix
 * (BROKER_A, BROKER_B, PROVIDER) and wraps the provider adapter so every
 * on-chain call's tx hash is printed with an explorer link.
 *
 * SDK: @virtuals-protocol/acp-node-v2 0.1.12. Note the create() input key is
 * `evmProvider` (the README's `provider:` is wrong, see clientFactory.js:5).
 */
import { AcpAgent, PrivyAlchemyEvmProviderAdapter } from "@virtuals-protocol/acp-node-v2";
import { base, baseSepolia } from "viem/chains";
import { log } from "./render.js";
import { need } from "./env.js";

export const CHAINS = { 8453: base, 84532: baseSepolia };
export const EXPLORER = { 8453: "https://basescan.org", 84532: "https://sepolia.basescan.org" };

export function chainId() {
  return Number(process.env.ACP_CHAIN_ID || 84532);
}

export function txUrl(chain, hash) {
  return `${EXPLORER[chain] || EXPLORER[8453]}/tx/${hash}`;
}

/** Wrap sendCalls so the hash of every ACP / ERC-8004 transaction is surfaced. */
function traceAdapter(adapter, label, txLog) {
  const orig = adapter.sendCalls.bind(adapter);
  adapter.sendCalls = async (chain, calls) => {
    const started = Date.now();
    const res = await orig(chain, calls);
    for (const h of [].concat(res)) {
      txLog.push({ chain, hash: h, label, at: new Date().toISOString() });
      log("CHAIN", `${label} tx ${h}  ${txUrl(chain, h)}  (${Date.now() - started} ms)`);
    }
    return res;
  };
  return adapter;
}

export async function createAgent(prefix, { label = prefix } = {}) {
  const txLog = [];
  const adapter = await PrivyAlchemyEvmProviderAdapter.create({
    walletAddress: need(`${prefix}_WALLET_ADDRESS`),
    walletId: need(`${prefix}_WALLET_ID`),
    signerPrivateKey: need(`${prefix}_SIGNER_PRIVATE_KEY`),
    chains: [base, baseSepolia],
    ...(process.env.BUILDER_CODE ? { builderCode: process.env.BUILDER_CODE } : {}),
  });
  traceAdapter(adapter, label, txLog);
  const agent = await AcpAgent.create({ evmProvider: adapter });
  const address = (await agent.getAddress()).toLowerCase();
  return { agent, adapter, address, txLog };
}

/** Fill an offering's JSON-schema requirement with our spec text. Best effort. */
export function fillRequirement(requirements, text) {
  if (typeof requirements === "string" || !requirements) return text;
  const props = requirements.properties || {};
  const out = {};
  for (const [k, def] of Object.entries(props)) {
    const t = def?.type;
    if (t === "string" || !t) out[k] = text;
    else if (t === "number" || t === "integer") out[k] = def.minimum ?? 1;
    else if (t === "boolean") out[k] = true;
    else if (t === "array") out[k] = [text];
    else out[k] = text;
  }
  return Object.keys(out).length ? out : text;
}
