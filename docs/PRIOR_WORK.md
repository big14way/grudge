# Prior work declaration

GRUDGE was written from scratch for the Sibyl Labs hackathon (September 2026).
Fresh `git init`, MIT license, no scaffolding from any existing repository.

## Studied

**Clawback** (github.com/EdwardJXLi/Clawback, ETHGlobal New York 2026). Two
ideas were studied there:

1. The two-tier agent / principal reputation idea: an agent's standing and the
   standing of the party behind it are tracked as separate things.
2. The payment-hook-into-escrow idea: settlement is gated by a hook that reads
   reputation before funds move.

The Clawback repository carries no license. No code was copied from it. GRUDGE
does not use an escrow contract at all (ACP v2 already escrows, runs the memo
state machine and settles), and its reputation is private per-counterparty
memory rather than an onchain score, so the designs diverge at the root.

## Fixed

Clawback's commitment hashing omits the chain id and the contract address from
the preimage, so its signatures are replayable across deployments. GRUDGE's
consortium commitment (`memory-service/grudge_memory/store.py`, `commitment()`)
is

```
keccak256(encodePacked(uint256 chainId, address reputationRegistry,
                       address brokerWallet, uint256 acpJobId, string verdict))
```

The same report on another chain or against another registry deployment hashes
differently. `tests/test_trust.py::test_commitment_binds_chain_and_registry`
checks it.

## Ideas that are GRUDGE's own

- Trust is a private vector between two agents, not a universal scalar. ERC-8004
  gives everyone the same public number; GRUDGE keeps the private half and
  trusts it over the public one.
- Memory as the decision engine: who to hire, what terms, what price are
  computed only from remembered outcomes. Delete the memory and the broker
  exits (`scripts/deletion_test.sh`).
- Dynamic storage tiers: journal-only until three samples or two failures,
  then promotion to a warm entity that is rewritten in place; status derived
  on read from live failures; decay toward a neutral prior.
- The consortium tenant: a redacted cross-broker signal so a broker that never
  met a provider still refuses it.

## Dependencies

- `sibyl-memory-client` 0.8.0 (MIT), Sibyl Labs.
- `@virtuals-protocol/acp-node-v2` 0.1.12 (ISC), Virtuals Protocol.
- `viem` (MIT).
- ERC-8004 registries on Base by the ERC-8004 authors.
