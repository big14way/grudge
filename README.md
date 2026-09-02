# GRUDGE

A broker agent that hires Virtuals ACP provider agents, where its own private
memory of past counterparties is the selection, pricing and terms engine.

Public ERC-8004 reputation gives every buyer the same global score. GRUDGE
keeps a private per-counterparty trust vector in Sibyl Memory and trusts it
over the public number. Delete the memory layer and GRUDGE cannot rank, price,
or set terms. It exits. That is the design, not a degradation.

Built from scratch for the Sibyl Labs hackathon, September 2026.

## Status

Day 1: trust vector schema proposed in [docs/TRUST_VECTOR.md](docs/TRUST_VECTOR.md).
Sibyl client API verified against `sibyl-memory-client` 0.8.0 source.

## Layout

```
memory-service/   Python. Sole writer of the SQLite file. HTTP on localhost.
broker/           Node. ACP buyer agents (broker A, broker B). Memory clients only.
scripts/          deletion_test.sh and demo runners.
docs/             schema, demo script, prior work declaration.
```

## License

MIT. See [LICENSE](LICENSE).
