"""Pure trust math. No I/O. Everything here is unit tested in tests/test_trust.py.

The three decisions (who, terms, price) are functions of the trust vector.
No trust vector, no decision. There is deliberately no default path that
produces a decision from a public score alone.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import config as C

DIMENSIONS = ("spec_adherence", "latency", "refund_behavior", "price_drift")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ewma(prev: float | None, obs: float, alpha: float = C.EWMA_ALPHA) -> float:
    """First observation initialises directly; later ones blend."""
    if prev is None:
        return clamp(obs)
    return clamp(prev + alpha * (obs - prev))


def decay_toward_prior(value: float, days: float, half_life: float = C.DECAY_HALF_LIFE_DAYS) -> float:
    if days <= 0:
        return value
    return C.PRIOR + (value - C.PRIOR) * (0.5 ** (days / half_life))


def new_vector() -> dict[str, Any]:
    return {
        "schema_version": C.SCHEMA_VERSION,
        "trust": {d: C.PRIOR for d in DIMENSIONS},
        "observed": {d: 0 for d in DIMENSIONS},   # how many observations fed each dimension
        "per_category_competence": {},
        "sample_count": 0,
        "failures": [],
        "last_seen": None,
        "decayed_at": None,
        "public_score_at_last_job": None,
        "promoted_at": None,
        "promoted_from": None,
    }


# ---------------------------------------------------------------------------
# Observations from a single job outcome
# ---------------------------------------------------------------------------

def latency_obs(latency_s: float | None, sla_s: float | None) -> float | None:
    if latency_s is None or not sla_s:
        return None
    over = max(0.0, latency_s - sla_s)
    return clamp(1.0 - over / sla_s)


def price_drift_obs(quoted: float | None, charged: float | None) -> float | None:
    if quoted is None or charged is None or quoted <= 0:
        return None
    return 1.0 - clamp((charged - quoted) / quoted)


def is_failure(score: float | None, action: str | None) -> bool:
    if action == "disputed":
        return True
    return score is not None and score < C.FAIL_SCORE


def apply_outcome(vec: dict[str, Any], outcome: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Rewrite the vector in place with one job's observations. Returns vec.

    outcome keys: acp_job_id, category, score, action, latency_s, sla_s,
    quoted_price_usdc, charged_price_usdc, refunded (bool|None), reason,
    public_score (dict|None), ts (ISO, optional).
    """
    ts = outcome.get("ts") or iso(now)
    trust = vec["trust"]
    observed = vec.setdefault("observed", {d: 0 for d in DIMENSIONS})

    def feed(dim: str, obs: float | None) -> None:
        if obs is None:
            return
        prev = trust[dim] if observed[dim] > 0 else None
        trust[dim] = round(ewma(prev, obs), 4)
        observed[dim] += 1

    score = outcome.get("score")
    feed("spec_adherence", score)
    feed("latency", latency_obs(outcome.get("latency_s"), outcome.get("sla_s")))
    feed("price_drift", price_drift_obs(outcome.get("quoted_price_usdc"), outcome.get("charged_price_usdc")))
    refunded = outcome.get("refunded")
    if refunded is not None:
        feed("refund_behavior", 1.0 if refunded else 0.0)

    cat = outcome.get("category")
    if cat and score is not None:
        comp = vec["per_category_competence"]
        comp[cat] = round(ewma(comp.get(cat), score), 4)

    vec["sample_count"] = int(vec.get("sample_count", 0)) + 1
    vec["last_seen"] = ts
    if vec.get("decayed_at") is None:
        vec["decayed_at"] = ts
    if outcome.get("public_score") is not None:
        vec["public_score_at_last_job"] = outcome["public_score"]

    if is_failure(score, outcome.get("action")):
        vec["failures"].append({
            "acp_job_id": outcome.get("acp_job_id"),
            "ts": ts,
            "category": cat,
            "reason": outcome.get("reason") or f"evaluator score {score}",
        })
        vec["failures"] = vec["failures"][-C.MAX_FAILURES_KEPT:]
    return vec


# ---------------------------------------------------------------------------
# Decay and status, evaluated on read
# ---------------------------------------------------------------------------

def live_failures(vec: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    out = []
    for f in vec.get("failures", []):
        age_days = (now - parse_iso(f["ts"])).total_seconds() / 86400.0
        if age_days <= C.FAILURE_TTL_DAYS:
            out.append(f)
    return out


def derive_status(vec: dict[str, Any], now: datetime) -> str:
    n = len(live_failures(vec, now))
    if n >= C.BLACKLIST_AT_FAILURES:
        return C.STATUS_BLACKLISTED
    if n >= C.PROBATION_AT_FAILURES:
        return C.STATUS_PROBATION
    return C.STATUS_TRUSTED


def apply_decay(vec: dict[str, Any], now: datetime) -> tuple[dict[str, Any], bool]:
    """Decay every dimension toward the prior. Returns (vec, changed)."""
    ref = vec.get("decayed_at") or vec.get("last_seen")
    if ref is None:
        return vec, False
    days = (now - parse_iso(ref)).total_seconds() / 86400.0
    if days < 1.0:
        return vec, False
    for d in DIMENSIONS:
        vec["trust"][d] = round(decay_toward_prior(vec["trust"][d], days), 4)
    for c, v in list(vec["per_category_competence"].items()):
        vec["per_category_competence"][c] = round(decay_toward_prior(v, days), 4)
    vec["decayed_at"] = iso(now)
    return vec, True


def should_promote(sample_count: int, failure_count: int) -> bool:
    return sample_count >= C.PROMOTE_AT_SAMPLES or failure_count >= C.PROMOTE_AT_FAILURES


# ---------------------------------------------------------------------------
# The three decisions
# ---------------------------------------------------------------------------

def private_score(vec: dict[str, Any], category: str | None) -> float:
    t = vec["trust"]
    comp = vec["per_category_competence"].get(category, C.PRIOR) if category else C.PRIOR
    s = (C.WEIGHTS["spec_adherence"] * t["spec_adherence"]
         + C.WEIGHTS["category_competence"] * comp
         + C.WEIGHTS["latency"] * t["latency"]
         + C.WEIGHTS["refund_behavior"] * t["refund_behavior"]
         + C.WEIGHTS["price_drift"] * t["price_drift"])
    return round(s, 4)


def risk_premium(score: float, observed_max_drift: float = 0.0) -> float:
    base = (C.PREMIUM_PIVOT - score) * C.PREMIUM_SLOPE
    return round(clamp(base + observed_max_drift, 0.0, C.PREMIUM_MAX), 4)


def terms_for(status: str, score: float, base_size_usdc: float) -> dict[str, Any]:
    if status == C.STATUS_BLACKLISTED:
        return {"max_job_usdc": 0.0, "staged": None, "stages": 0,
                "require_evaluator": None, "retry_budget": 0}
    if status == C.STATUS_PROBATION:
        return {"max_job_usdc": round(base_size_usdc * C.SIZE_CAP_PROBATION, 6),
                "staged": True, "stages": C.STAGES_WHEN_STAGED,
                "require_evaluator": True, "retry_budget": C.RETRY_PROBATION}
    if status == C.STATUS_UNKNOWN:
        return {"max_job_usdc": round(base_size_usdc * C.SIZE_CAP_UNKNOWN, 6),
                "staged": True, "stages": C.STAGES_WHEN_STAGED,
                "require_evaluator": True, "retry_budget": C.RETRY_UNKNOWN}
    staged = score < C.STAGED_BELOW
    return {"max_job_usdc": round(base_size_usdc * (C.SIZE_CAP_TRUSTED_FLOOR + score), 6),
            "staged": staged, "stages": C.STAGES_WHEN_STAGED if staged else 1,
            "require_evaluator": score < C.EVALUATOR_BELOW, "retry_budget": C.RETRY_TRUSTED}


STATUS_RANK = {C.STATUS_TRUSTED: 0, C.STATUS_UNKNOWN: 1, C.STATUS_PROBATION: 2, C.STATUS_BLACKLISTED: 3}
