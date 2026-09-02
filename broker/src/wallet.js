/**
 * Wallet and registry helper.
 *   node src/wallet.js whoami                       auth each agent, show ACP registry entry, offerings, balances
 *   node src/wallet.js send-usdc --from BROKER_A --to 0x.. --amount 0.5 [--chain 84532]
 */
import { parseArgs } from "node:util";
import { createPublicClient, encodeFunctionData, erc20Abi, http, parseUnits, formatUnits } from "viem";
import { base, baseSepolia } from "viem/chains";
import { USDC_ADDRESSES } from "@virtuals-protocol/acp-node-v2";
import { loadEnv } from "./env.js";
import { createAgent } from "./acp.js";
import { log, short } from "./render.js";

loadEnv();
const { positionals, values: a } = parseArgs({
  allowPositionals: true,
  options: { from: { type: "string", default: "BROKER_A" }, to: { type: "string" }, amount: { type: "string" }, chain: { type: "string", default: process.env.ACP_CHAIN_ID || "84532" } },
});

const TOKENS = {
  84532: [{ name: "ACP test USDC (Virtuals)", address: USDC_ADDRESSES[84532] }, { name: "Circle faucet USDC", address: "0x036CbD53842c5426634e7929541eC2318f3dCF7e" }],
  8453: [{ name: "USDC", address: USDC_ADDRESSES[8453] }],
};
const clients = {
  84532: createPublicClient({ chain: baseSepolia, transport: http("https://sepolia.base.org") }),
  8453: createPublicClient({ chain: base, transport: http(process.env.BASE_RPC_URL || "https://base-rpc.publicnode.com") }),
};

async function balances(address) {
  const out = [];
  for (const [chain, toks] of Object.entries(TOKENS)) {
    for (const t of toks) {
      try {
        const [bal, dec] = await Promise.all([
          clients[chain].readContract({ address: t.address, abi: erc20Abi, functionName: "balanceOf", args: [address] }),
          clients[chain].readContract({ address: t.address, abi: erc20Abi, functionName: "decimals" }),
        ]);
        out.push(`${chain}:${t.name}=${formatUnits(bal, dec)}`);
      } catch (e) { out.push(`${chain}:${t.name}=? (${(e.shortMessage || e.message).slice(0, 40)})`); }
    }
  }
  return out.join("  ");
}

async function whoami() {
  for (const prefix of ["BROKER_A", "BROKER_B", "PROVIDER"]) {
    try {
      const { agent, address } = await createAgent(prefix, { label: prefix });
      const me = await agent.getMe().catch((e) => ({ error: e.message }));
      log(prefix, `wallet ${address}`);
      if (me.error) log(prefix, `getMe failed: ${me.error}`);
      else {
        log(prefix, `registry: "${me.name}" role=${me.role} chains=${(me.chains || []).map((c) => c.chainId ?? c.id ?? JSON.stringify(c)).join(",")} offerings=${(me.offerings || []).length}`);
        for (const o of me.offerings || []) log(prefix, `  offering "${o.name}" ${o.priceType} ${o.priceValue} sla ${o.slaMinutes}m requiredFunds=${o.requiredFunds} hidden=${o.isHidden} requirements=${JSON.stringify(o.requirements).slice(0, 160)}`);
      }
      log(prefix, `balances ${await balances(address)}`);
      await agent.stop().catch(() => {});
    } catch (e) {
      log(prefix, `FAILED: ${e.shortMessage || e.message}`);
    }
  }
  process.exit(0);
}

async function sendUsdc() {
  const chain = Number(a.chain);
  const token = USDC_ADDRESSES[chain];
  const { adapter, address } = await createAgent(a.from, { label: a.from });
  const dec = await clients[chain].readContract({ address: token, abi: erc20Abi, functionName: "decimals" });
  const data = encodeFunctionData({ abi: erc20Abi, functionName: "transfer", args: [a.to, parseUnits(a.amount, dec)] });
  log(a.from, `sending ${a.amount} USDC (${short(token)}) on ${chain} from ${short(address)} to ${short(a.to)}`);
  const hash = await adapter.sendCalls(chain, [{ to: token, data, value: 0n }]);
  log(a.from, `done ${[].concat(hash)[0]}`);
  process.exit(0);
}

const cmd = positionals[0];
if (cmd === "whoami") whoami();
else if (cmd === "send-usdc" && a.to && a.amount) sendUsdc();
else { console.error("usage: node src/wallet.js whoami | send-usdc --from BROKER_A --to 0x.. --amount 0.5"); process.exit(2); }
