"""Every Sibyl Memory read and write in GRUDGE lives in this file.

One MemoryClient, one SQLite file, one process, one lock. Tenants are switched
under the lock with set_tenant(), so writes from broker A, broker B and the
consortium path are serialized and never contend for the WAL write lock.

Tier usage (see docs/TRUST_VECTOR.md):
  WARM  entities  category="counterparty"  one row per provider, rewritten in place
  COLD  journal   one event per job, fixed kwargs mapped: evaluated / acted / forward / extra
  HOT   state     negotiation:<job> and inflight only
  REF   reference spec:<category> acceptance criteria
  consortium tenant, category="signal": redacted cross-broker signal

Every operation prints a [MEMORY] line so a judge can watch the tiers move.
"""
from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime
from typing import Any, Callable

from sibyl_memory_client import MemoryClient, NotFoundError
from sibyl_memory_client.multi_record import multi_record_search

from . import config as C
from . import trust as T
from .evaluator import DEFAULT_SPECS, evaluate
from .keccak import keccak256_hex

DEFAULT_CHAIN_ID = 8453
DEFAULT_REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
ZERO_ADDRESS = "0x" + "00" * 20


def load_sibyl_credentials(path: str | None = None) -> dict[str, Any]:
    """Read ~/.sibyl-memory/credentials.json written by `sibyl init`, if present.

    Passing account_id / session_token / tier to the client is what lets Sibyl
    verify the tier server-side and count our memory operations (the usage
    heartbeat is a no-op for un-activated installs). Absent file = free tier,
    fully local, which is how the tests run.
    """
    p = os.path.expanduser(path or os.environ.get("GRUDGE_SIBYL_CREDENTIALS", "~/.sibyl-memory/credentials.json"))
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: raw.get(k) for k in ("account_id", "session_token", "tier", "tenant_id", "wallet", "email")}


def _addr(a: str) -> str:
    a = (a or "").strip().lower()
    if not (a.startswith("0x") and len(a) == 42):
        raise ValueError(f"not an EVM address: {a!r}")
    return a


def _hexbytes(a: str, n: int) -> bytes:
    return bytes.fromhex(a[2:].rjust(n * 2, "0"))


def commitment(chain_id: int, registry: str, broker: str, job_id: int, verdict: str) -> str:
    """keccak256(encodePacked(uint256 chainId, address registry, address broker, uint256 jobId, string verdict)).

    chainId and the registry address are in the preimage on purpose: the same
    report on another chain or another registry deployment hashes differently,
    so it cannot be replayed. Matches viem encodePacked + keccak256.
    """
    pre = (int(chain_id).to_bytes(32, "big") + _hexbytes(registry.lower(), 20)
           + _hexbytes(broker.lower(), 20) + int(job_id).to_bytes(32, "big")
           + verdict.encode("utf-8"))
    return keccak256_hex(pre)


class MemoryStore:
    def __init__(self, db_path: str, *, now_fn: Callable[[], datetime] | None = None,
                 log: Callable[[str], None] | None = None) -> None:
        self._db_path = os.path.expanduser(db_path)
        creds = load_sibyl_credentials()
        self._client = MemoryClient.local(
            self._db_path, tenant_id="broker-a", tier=creds.get("tier") or "free",
            account_id=creds.get("account_id"), session_token=creds.get("session_token"),
        )
        self.account = creds.get("account_id")
        self._lock = threading.RLock()
        self._now = now_fn or T.utc_now
        self._log = log or (lambda s: print(s, flush=True))
        self.reads = 0
        self.writes = 0
        self.log_lines: deque[tuple[int, str]] = deque(maxlen=500)   # ring buffer for the viewer
        self._log_seq = 0

    # ------------------------------------------------------------------ util
    def _mem(self, kind: str, msg: str) -> None:
        if kind == "read":
            self.reads += 1
        elif kind == "write":
            self.writes += 1
        line = f"[MEMORY] {kind:<7} {msg}"
        self._log_seq += 1
        self.log_lines.append((self._log_seq, f"{T.iso(self._now())} {line}"))
        self._log(line)

    def _use(self, tenant: str) -> MemoryClient:
        if self._client.get_tenant() != tenant:
            self._client.set_tenant(tenant)
        return self._client

    @property
    def db_path(self) -> str:
        return self._db_path

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"db": self._db_path, "reads": self.reads, "writes": self.writes,
                    "free_tier": self._client.free_tier_status()}

    # ------------------------------------------------------- REFERENCE tier
    def seed_references(self, tenant: str) -> list[str]:
        seeded = []
        with self._lock:
            c = self._use(tenant)
            for cat, spec in DEFAULT_SPECS.items():
                key = f"spec:{cat}"
                if c.get_reference(key) is None:
                    c.set_reference(key, spec, metadata={"schema_version": C.SCHEMA_VERSION})
                    self._mem("write", f"tenant={tenant} reference {key} seeded ({len(spec['criteria'])} criteria)")
                    seeded.append(key)
        return seeded

    def get_spec(self, tenant: str, category: str) -> dict[str, Any] | None:
        with self._lock:
            c = self._use(tenant)
            ref = c.get_reference(f"spec:{category}")
            self._mem("read", f"tenant={tenant} reference spec:{category} {'hit' if ref else 'miss'}")
            if ref is None:
                return None
            body = ref["body"]
            return json.loads(body) if isinstance(body, str) else body

    def set_spec(self, tenant: str, category: str, spec: dict[str, Any]) -> None:
        with self._lock:
            c = self._use(tenant)
            c.set_reference(f"spec:{category}", spec, metadata={"schema_version": C.SCHEMA_VERSION})
            self._mem("write", f"tenant={tenant} reference spec:{category} rewritten")

    # ------------------------------------------------------------- HOT tier
    def set_state(self, tenant: str, key: str, body: dict[str, Any]) -> None:
        with self._lock:
            self._use(tenant).set_state(key, body)
            self._mem("write", f"tenant={tenant} state {key}")

    def get_state(self, tenant: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            doc = self._use(tenant).get_state(key)
            self._mem("read", f"tenant={tenant} state {key} {'hit' if doc else 'miss'}")
            return doc["body"] if doc else None

    def _clear_negotiation(self, tenant: str, job_id: Any) -> None:
        c = self._use(tenant)
        key = f"negotiation:{job_id}"
        if c.get_state(key) is not None:
            c.set_state(key, {"closed": True, "closed_at": T.iso(self._now())})
            self._mem("write", f"tenant={tenant} state {key} closed")
        inflight = c.get_state("inflight")
        jobs = [j for j in (inflight["body"].get("jobs", []) if inflight else []) if str(j) != str(job_id)]
        c.set_state("inflight", {"jobs": jobs})
        self._mem("write", f"tenant={tenant} state inflight -> {len(jobs)} open")

    def mark_inflight(self, tenant: str, job_id: Any, negotiation: dict[str, Any]) -> None:
        with self._lock:
            c = self._use(tenant)
            c.set_state(f"negotiation:{job_id}", negotiation)
            inflight = c.get_state("inflight")
            jobs = inflight["body"].get("jobs", []) if inflight else []
            if str(job_id) not in [str(j) for j in jobs]:
                jobs.append(job_id)
            c.set_state("inflight", {"jobs": jobs})
            self._mem("write", f"tenant={tenant} state negotiation:{job_id} + inflight ({len(jobs)} open)")

    # ------------------------------------------------------------ COLD tier
    def journal_for(self, tenant: str, address: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """All journal events for one provider, oldest first.

        read_events() has no provider filter, so this goes through the FTS
        index with tiers=("journal",) and then verifies extra.provider on every
        hit, because search is fuzzy by design.
        """
        address = _addr(address)
        with self._lock:
            hits = self._use(tenant).search(address, tiers=("journal",), limit=limit)
            rows = []
            for h in hits:
                body = h.get("body") or {}
                extra = body.get("extra") or {}
                if str(extra.get("provider", "")).lower() == address:
                    rows.append({"id": h["key"], "ts": h["ts"], **body})
            rows.sort(key=lambda r: r["ts"])
            self._mem("read", f"tenant={tenant} journal search provider={address[:10]} "
                              f"hits={len(hits)} verified={len(rows)}")
            return rows

    def recent_events(self, tenant: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ev = self._use(tenant).read_events(limit=limit)
            self._mem("read", f"tenant={tenant} journal read_events limit={limit} -> {len(ev)}")
            return ev

    # ------------------------------------------------------------ WARM tier
    def get_counterparty(self, tenant: str, address: str) -> tuple[dict[str, Any] | None, str]:
        """Warm read with decay-on-read. Returns (vector, status).

        status is recomputed from live failures on every read. If decay or
        expiry changed anything, the entity is rewritten in place so the
        stored row never drifts from what the engine believes.
        """
        address = _addr(address)
        now = self._now()
        with self._lock:
            c = self._use(tenant)
            try:
                row = c.get_entity(C.CATEGORY_COUNTERPARTY, address)
            except NotFoundError:
                self._mem("read", f"tenant={tenant} entity counterparty/{address[:10]} miss -> unknown")
                return None, C.STATUS_UNKNOWN
            vec = row["body"]
            stored_status = row["status"]
            vec, decayed = T.apply_decay(vec, now)
            status = T.derive_status(vec, now)
            self._mem("read", f"tenant={tenant} entity counterparty/{address[:10]} status={stored_status} "
                              f"samples={vec.get('sample_count')} live_failures={len(T.live_failures(vec, now))}")
            if decayed or status != stored_status:
                c.set_entity(C.CATEGORY_COUNTERPARTY, address, vec, status=status)
                why = []
                if decayed:
                    why.append("trust decayed toward prior")
                if status != stored_status:
                    why.append(f"status {stored_status} -> {status} (failures expired)")
                self._mem("write", f"tenant={tenant} entity counterparty/{address[:10]} rewritten on read: {'; '.join(why)}")
            return vec, status

    def list_counterparties(self, tenant: str, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._use(tenant).list_entities(C.CATEGORY_COUNTERPARTY, status=status)
            self._mem("read", f"tenant={tenant} list entities counterparty status={status} -> {len(rows)}")
            return [{"address": r["name"], "status": r["status"], "vector": r["body"],
                     "updated_at": r["updated_at"]} for r in rows]

    # -------------------------------------------------------- consortium
    def consortium_signal(self, address: str) -> dict[str, Any] | None:
        address = _addr(address)
        with self._lock:
            c = self._use(C.TENANT_CONSORTIUM)
            try:
                row = c.get_entity(C.CATEGORY_SIGNAL, address)
            except NotFoundError:
                self._mem("read", f"tenant=consortium signal/{address[:10]} miss")
                return None
            sig = row["body"]
            now = self._now()
            live = [f for f in sig.get("failure_ts", [])
                    if (now - T.parse_iso(f)).total_seconds() / 86400.0 <= C.FAILURE_TTL_DAYS]
            sig["live_failures"] = len(live)
            self._mem("read", f"tenant=consortium signal/{address[:10]} status={row['status']} "
                              f"live_failures={len(live)} reporters={len(sig.get('reporters', []))}")
            return {**sig, "status": row["status"]}

    def _write_consortium_signal(self, reporter: str, address: str, status: str,
                                 category: str | None, ts: str, commit: str) -> None:
        """Redacted. No price, no job id, no spec text, no evaluator notes."""
        c = self._use(C.TENANT_CONSORTIUM)
        try:
            sig = c.get_entity(C.CATEGORY_SIGNAL, address)["body"]
        except NotFoundError:
            sig = {"failure_ts": [], "categories_failed": [], "reporters": [], "commitments": []}
        sig["failure_ts"] = (sig.get("failure_ts", []) + [ts])[-C.MAX_FAILURES_KEPT:]
        if category and category not in sig["categories_failed"]:
            sig["categories_failed"].append(category)
        if reporter not in sig["reporters"]:
            sig["reporters"].append(reporter)
        sig["commitments"] = (sig.get("commitments", []) + [commit])[-C.MAX_FAILURES_KEPT:]
        sig["last_failure_ts"] = ts
        now = self._now()
        live = [f for f in sig["failure_ts"] if (now - T.parse_iso(f)).total_seconds() / 86400.0 <= C.FAILURE_TTL_DAYS]
        sig_status = (C.STATUS_BLACKLISTED if len(live) >= C.BLACKLIST_AT_FAILURES
                      else C.STATUS_PROBATION if len(live) >= C.PROBATION_AT_FAILURES
                      else "watch")
        c.set_entity(C.CATEGORY_SIGNAL, address, sig, status=sig_status)
        self._mem("write", f"tenant=consortium signal/{address[:10]} status={sig_status} "
                           f"live_failures={len(live)} reporters={len(sig['reporters'])} (redacted, by {reporter})")

    # ------------------------------------------------------------ evaluate
    def evaluate_delivery(self, tenant: str, category: str, delivery: str | None) -> dict[str, Any]:
        spec = self.get_spec(tenant, category)
        if spec is None:
            raise KeyError(f"no reference spec for category {category!r}")
        result = evaluate(spec, delivery)
        result["category"] = category
        result["sla_seconds"] = spec.get("sla_seconds")
        return result

    # -------------------------------------------------------- record outcome
    def record_outcome(self, tenant: str, outcome: dict[str, Any]) -> dict[str, Any]:
        """One job resolved. Journal first, then warm rewrite or promotion,
        then the redacted consortium signal if it was a failure.

        outcome: provider, acp_job_id, category, score, action, reason,
                 latency_s, sla_s, quoted_price_usdc, charged_price_usdc,
                 refunded, tx_hash, chain_id, broker_wallet, public_score,
                 evaluation (dict from evaluate_delivery), lesson (str)
        """
        address = _addr(outcome["provider"])
        now = self._now()
        ts = T.iso(now)
        score = outcome.get("score")
        action = outcome.get("action") or "released"
        failure = T.is_failure(score, action)
        category = outcome.get("category")
        with self._lock:
            c = self._use(tenant)
            evaluation = outcome.get("evaluation") or {"score": score}
            tags = [t for t in (category, "specfail" if failure else "specok",
                                "disputed" if action == "disputed" else None,
                                "overcharged" if (outcome.get("charged_price_usdc") or 0) > (outcome.get("quoted_price_usdc") or 0) else None,
                                "late" if (outcome.get("latency_s") or 0) > (outcome.get("sla_s") or float("inf")) else None) if t]
            # COLD: the fixed kwargs are mapped deliberately, see docs/TRUST_VECTOR.md
            event_id = c.write_event(
                evaluated={"score": score, "criteria_met": evaluation.get("criteria_met"),
                           "criteria_total": evaluation.get("criteria_total"),
                           "unmet": evaluation.get("unmet"), "notes": evaluation.get("notes"),
                           "sample": (evaluation.get("sample") or "")[:400] or None},   # so any judgement can be audited
                acted={"action": action, "provider": address, "why": outcome.get("reason")},
                forward={"lesson": outcome.get("lesson") or
                         ("tighten terms for this provider" if failure else "terms can loosen for this provider"),
                         "failure": failure},
                extra={"acp_job_id": outcome.get("acp_job_id"), "provider": address, "category": category,
                       "quoted_price_usdc": outcome.get("quoted_price_usdc"),
                       "charged_price_usdc": outcome.get("charged_price_usdc"),
                       "latency_s": outcome.get("latency_s"), "sla_s": outcome.get("sla_s"),
                       "tx_hash": outcome.get("tx_hash"), "chain_id": outcome.get("chain_id"),
                       "refunded": outcome.get("refunded"), "tags": tags},
                ts=ts,
            )
            self._mem("write", f"tenant={tenant} journal event {event_id[:8]} job={outcome.get('acp_job_id')} "
                               f"provider={address[:10]} action={action} score={score} tags={tags}")

            promoted = False
            try:
                row = c.get_entity(C.CATEGORY_COUNTERPARTY, address)
                vec = row["body"]
                self._mem("read", f"tenant={tenant} entity counterparty/{address[:10]} status={row['status']} (pre-rewrite)")
                T.apply_outcome(vec, {**outcome, "ts": ts}, now)
                status = T.derive_status(vec, now)
                c.set_entity(C.CATEGORY_COUNTERPARTY, address, vec, status=status)
                self._mem("write", f"tenant={tenant} entity counterparty/{address[:10]} REWRITTEN IN PLACE "
                                   f"samples={vec['sample_count']} trust={vec['trust']} status={row['status']} -> {status}")
            except NotFoundError:
                events = self.journal_for(tenant, address)
                fails = [e for e in events if (e.get("forward") or {}).get("failure")]
                if T.should_promote(len(events), len(fails)):
                    vec = self._rebuild_from_journal(events, now)
                    vec["promoted_at"] = ts
                    vec["promoted_from"] = "journal"
                    if outcome.get("public_score") is not None:
                        vec["public_score_at_last_job"] = outcome["public_score"]
                    status = T.derive_status(vec, now)
                    c.set_entity(C.CATEGORY_COUNTERPARTY, address, vec, status=status)
                    promoted = True
                    self._mem("write", f"tenant={tenant} PROMOTE journal -> entity counterparty/{address[:10]} "
                                       f"after {len(events)} samples / {len(fails)} failures, status={status}")
                else:
                    vec, status = None, C.STATUS_UNKNOWN
                    self._mem("read", f"tenant={tenant} counterparty/{address[:10]} stays journal-only "
                                      f"({len(events)}/{C.PROMOTE_AT_SAMPLES} samples, {len(fails)}/{C.PROMOTE_AT_FAILURES} failures)")

            commit = None
            if failure and tenant != C.TENANT_CONSORTIUM:
                commit = commitment(outcome.get("chain_id") or DEFAULT_CHAIN_ID,
                                    outcome.get("reputation_registry") or DEFAULT_REPUTATION_REGISTRY,
                                    outcome.get("broker_wallet") or ZERO_ADDRESS,
                                    int(outcome.get("acp_job_id") or 0), "specfail")
                self._write_consortium_signal(tenant, address, status, category, ts, commit)

            self._use(tenant)
            self._clear_negotiation(tenant, outcome.get("acp_job_id"))
            return {"event_id": event_id, "failure": failure, "promoted": promoted, "status": status,
                    "vector": vec, "commitment": commit, "ts": ts}

    def _rebuild_from_journal(self, events: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
        vec = T.new_vector()
        for e in events:
            ev, ac, ex = e.get("evaluated") or {}, e.get("acted") or {}, e.get("extra") or {}
            T.apply_outcome(vec, {
                "acp_job_id": ex.get("acp_job_id"), "category": ex.get("category"),
                "score": ev.get("score"), "action": ac.get("action"), "reason": ev.get("notes"),
                "latency_s": ex.get("latency_s"), "sla_s": ex.get("sla_s"),
                "quoted_price_usdc": ex.get("quoted_price_usdc"), "charged_price_usdc": ex.get("charged_price_usdc"),
                "refunded": ex.get("refunded"), "ts": e.get("ts"),
            }, now)
        return vec

    # -------------------------------------------------------------- decide
    def decide(self, tenant: str, job: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """WHO, WHAT TERMS, WHAT PRICE for one job. Memory in, decision out.

        job: {category, budget_usdc, sla_seconds?}
        candidates: [{address, public_score?, offering?, quoted_price_usdc}]
        """
        category = job["category"]
        budget = float(job.get("budget_usdc", 0))
        spec = self.get_spec(tenant, category) or {}
        base_size = float(spec.get("base_size_usdc", budget or 0.1))
        now = self._now()
        ranked = []
        for cand in candidates:
            address = _addr(cand["address"])
            quoted = float(cand.get("quoted_price_usdc", 0))
            public = cand.get("public_score")
            evidence: dict[str, Any] = {}
            refuse: str | None = None

            vec, status = self.get_counterparty(tenant, address)
            if vec is None:
                events = self.journal_for(tenant, address)
                vec = self._rebuild_from_journal(events, now) if events else T.new_vector()
                evidence["journal_samples"] = len(events)
                sig = self.consortium_signal(address)
                if sig and sig["live_failures"] >= C.CONSORTIUM_REFUSE_AT and tenant not in sig.get("reporters", []):
                    refuse = (f"consortium: {sig['live_failures']} live failures in "
                              f"{sig.get('categories_failed')} reported by {sig.get('reporters')}, "
                              f"last {sig.get('last_failure_ts')}; we never met them and will not be first")
                    evidence["consortium"] = sig

            live = T.live_failures(vec, now)
            evidence["live_failures"] = live
            evidence["sample_count"] = vec.get("sample_count", 0)
            evidence["last_seen"] = vec.get("last_seen")
            evidence["public_score_at_last_job"] = vec.get("public_score_at_last_job")

            # cross-tier search: dispute window and price drift span journal + entity
            with self._lock:
                hits = self._use(tenant).search(address, limit=50)
            trouble, max_drift = False, 0.0
            for h in hits:
                if h.get("tier") != "journal":
                    continue
                b = h.get("body") or {}
                ex = b.get("extra") or {}
                if str(ex.get("provider", "")).lower() != address:
                    continue
                age = (now - T.parse_iso(h["ts"])).total_seconds() / 86400.0
                if age <= C.FAILURE_TTL_DAYS and any(t in (ex.get("tags") or []) for t in ("specfail", "disputed", "overcharged")):
                    trouble = True
                q, ch = ex.get("quoted_price_usdc"), ex.get("charged_price_usdc")
                if q and ch and ch > q:
                    max_drift = max(max_drift, T.clamp((ch - q) / q))
            self._mem("read", f"tenant={tenant} cross-tier search {address[:10]} hits={len(hits)} "
                              f"trouble={trouble} max_drift={max_drift:.2f}")

            score = T.private_score(vec, category)
            premium = T.risk_premium(score, max_drift)
            max_price = round(budget * (1 - premium), 6)
            terms = T.terms_for(status, score, base_size)
            terms["dispute_window_s"] = C.DISPUTE_WINDOW_BASE_S * (C.DISPUTE_WINDOW_TROUBLE_MULT if trouble else 1)

            if refuse is None:
                if status == C.STATUS_BLACKLISTED:
                    f = live[-1]
                    refuse = (f"blacklisted: {len(live)} live failures, latest job {f['acp_job_id']} on {f['ts']} "
                              f"({f['reason']})")
                elif status == C.STATUS_PROBATION and any(f.get("category") == category for f in live):
                    f = [x for x in live if x.get("category") == category][-1]
                    refuse = (f"probation in {category}: burned us on job {f['acp_job_id']} on {f['ts']} "
                              f"({f['reason']}); public score {public} ignored")
                elif quoted > max_price:
                    refuse = f"price: quoted {quoted} > max {max_price} after {premium:.0%} private risk premium"
                elif quoted > terms["max_job_usdc"]:
                    refuse = f"size: quoted {quoted} > job cap {terms['max_job_usdc']} for status {status}"

            ranked.append({
                "address": address, "public_score": public, "offering": cand.get("offering"),
                "quoted_price_usdc": quoted, "status": status, "private_score": score,
                "risk_premium": premium, "max_price_usdc": max_price, "terms": terms,
                "verdict": "refuse" if refuse else "hire", "reason": refuse or
                    f"{status}, private {score:.2f}, premium {premium:.0%}, cap {terms['max_job_usdc']}",
                "evidence": evidence,
            })

        ranked.sort(key=lambda r: (r["verdict"] != "hire", T.STATUS_RANK.get(r["status"], 9),
                                   -r["private_score"], -(r["public_score"] or 0)))
        chosen = next((r for r in ranked if r["verdict"] == "hire"), None)

        # The counterfactual, stated outright: a broker with no memory has one input (the
        # public score) and one policy (top score, flat terms, full budget, no evaluator).
        memoryless = max(ranked, key=lambda r: (r["public_score"] or 0)) if ranked else None
        counterfactual = None
        if memoryless is not None:
            counterfactual = {
                "address": memoryless["address"], "public_score": memoryless["public_score"],
                "terms": {"max_job_usdc": budget, "staged": False, "stages": 1, "require_evaluator": False,
                          "retry_budget": 0, "dispute_window_s": 0},
                "max_price_usdc": budget,
                "memory_says": memoryless["status"], "live_failures": len(memoryless["evidence"].get("live_failures", [])),
                "same_as_memory": bool(chosen and chosen["address"] == memoryless["address"]),
                "delta": {},
            }
            if chosen:
                ct, mt = chosen["terms"], counterfactual["terms"]
                counterfactual["delta"] = {
                    "provider_changed": chosen["address"] != memoryless["address"],
                    "escrow_cap": f"{mt['max_job_usdc']} -> {ct['max_job_usdc']}",
                    "max_price": f"{budget} -> {chosen['max_price_usdc']}",
                    "staged": f"{mt['stages']} -> {ct['stages']}", "evaluator": f"no -> {'yes' if ct['require_evaluator'] else 'no'}",
                    "retries": f"0 -> {ct['retry_budget']}", "dispute_window_s": f"0 -> {ct['dispute_window_s']}",
                }
        self._mem("read", f"tenant={tenant} DECIDE {category}: "
                          + (f"hire {chosen['address'][:10]} ({chosen['status']}, private {chosen['private_score']})"
                             if chosen else "no acceptable provider")
                          + f"; refused {sum(1 for r in ranked if r['verdict'] == 'refuse')}/{len(ranked)}"
                          + (f" | MEMORYLESS would hire {memoryless['address'][:10]} (public {memoryless['public_score']}, "
                             f"flat terms, {len(memoryless['evidence'].get('live_failures', []))} live failures known to us)" if memoryless else ""))
        return {"job": job, "ranked": ranked, "chosen": chosen, "counterfactual": counterfactual, "decided_at": T.iso(now)}

    # --------------------------------------------------------------- viewer
    def snapshot(self, *, events: int = 15) -> dict[str, Any]:
        """Read-only view for the terminal viewer. Bypasses _mem on purpose:
        the viewer must not count as memory traffic, must not trigger
        decay rewrites, and must not appear in the [MEMORY] log."""
        now = self._now()
        out: dict[str, Any] = {"now": T.iso(now), "db": self._db_path, "reads": self.reads, "writes": self.writes,
                               "tier": self._client.get_tier(), "account": self.account, "tenants": {}}
        with self._lock:
            for tenant in ("broker-a", "broker-b"):
                c = self._use(tenant)
                rows = []
                for r in c.list_entities(C.CATEGORY_COUNTERPARTY, limit=50):
                    v = r["body"]
                    live = T.live_failures(v, now)
                    rows.append({"address": r["name"], "status": r["status"], "trust": v.get("trust"),
                                 "competence": v.get("per_category_competence"), "samples": v.get("sample_count"),
                                 "live_failures": len(live), "last_failure": live[-1] if live else None,
                                 "last_seen": v.get("last_seen"), "public": v.get("public_score_at_last_job"),
                                 "updated_at": r["updated_at"]})
                inflight = c.get_state("inflight")
                out["tenants"][tenant] = {"counterparties": rows, "events": c.read_events(limit=events),
                                          "inflight": (inflight or {}).get("body", {}).get("jobs", [])}
            c = self._use(C.TENANT_CONSORTIUM)
            sigs = []
            for r in c.list_entities(C.CATEGORY_SIGNAL, limit=50):
                b = r["body"]
                live = [f for f in b.get("failure_ts", []) if (now - T.parse_iso(f)).total_seconds() / 86400.0 <= C.FAILURE_TTL_DAYS]
                sigs.append({"address": r["name"], "status": r["status"], "live_failures": len(live),
                             "categories_failed": b.get("categories_failed"), "reporters": b.get("reporters"),
                             "last_failure_ts": b.get("last_failure_ts"), "commitments": len(b.get("commitments", []))})
            out["consortium"] = sigs
            out["free_tier"] = self._client.free_tier_status()
        return out

    def log_after(self, seq: int) -> list[dict[str, Any]]:
        return [{"seq": n, "line": l} for n, l in self.log_lines if n > seq]

    # --------------------------------------------------------- multi record
    def multi_query(self, tenant: str, query: str, *, limit: int = 10) -> dict[str, Any]:
        """Question spanning linked records, e.g. "which providers that failed a
        research job also overcharged". Three stages, all logged:
          1. Sibyl retrieve   (FTS over journal + entity + state + reference)
          2. Sibyl verify     (coverage / anchor gates inside multi_record_search)
          3. GRUDGE exact     (every query token must appear in the record)
        Stage 2 deliberately admits partial-coverage records so the caller can
        see near-misses; stage 3 is what the answer is built from.
        """
        diag: dict[str, Any] = {}
        tokens = [t for t in query.lower().split() if t]
        with self._lock:
            hits = multi_record_search(self._use(tenant), query, limit=limit, diagnostics=diag)
            verdict = getattr(hits, "verdict", None)
            self._mem("read", f"tenant={tenant} multi_record_search {query!r} stage1 retrieve -> "
                              f"stage2 verify: {len(hits)} hits, verdict={getattr(verdict, 'code', verdict)}, "
                              f"coverage={diag.get('coverage')}, abstained_on={diag.get('abstained_on')}")
            exact, providers = [], set()
            for h in hits:
                text = json.dumps(h.get("body"), default=str).lower()
                covered = [t for t in tokens if t in text]
                full = len(covered) == len(tokens)
                if full:
                    exact.append(h)
                    if h.get("tier") == "journal":
                        providers.add(str(((h.get("body") or {}).get("extra") or {}).get("provider")))
                self._mem("read", f"tenant={tenant}   stage3 exact {h.get('tier')}/{str(h.get('key'))[:10]} "
                                  f"coverage={len(covered)}/{len(tokens)} {'KEEP' if full else 'drop'}")
            return {"query": query, "hits": [dict(h) for h in hits], "exact": [dict(h) for h in exact],
                    "providers": sorted(providers), "verdict": str(getattr(verdict, "code", verdict)),
                    "diagnostics": {k: v for k, v in diag.items() if k != "verdict"}}
