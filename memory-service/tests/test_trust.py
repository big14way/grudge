from datetime import datetime, timedelta, timezone

from grudge_memory import config as C
from grudge_memory import trust as T
from grudge_memory.keccak import keccak256_hex
from grudge_memory.store import commitment

NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_ewma_first_then_blend():
    assert T.ewma(None, 0.9) == 0.9
    assert abs(T.ewma(0.9, 0.1) - (0.9 + 0.35 * (0.1 - 0.9))) < 1e-9


def test_decay_halves_distance_to_prior_at_half_life():
    assert abs(T.decay_toward_prior(0.9, 14.0) - 0.7) < 1e-9
    assert T.decay_toward_prior(0.9, 0) == 0.9
    assert abs(T.decay_toward_prior(0.1, 28.0) - 0.4) < 1e-9


def test_observations():
    assert T.latency_obs(300, 900) == 1.0
    assert T.latency_obs(1800, 900) == 0.0
    assert abs(T.latency_obs(1350, 900) - 0.5) < 1e-9
    assert T.latency_obs(None, 900) is None
    assert T.price_drift_obs(0.01, 0.01) == 1.0
    assert abs(T.price_drift_obs(0.01, 0.015) - 0.5) < 1e-9
    assert T.price_drift_obs(0.01, 0.05) == 0.0


def test_failure_rule():
    assert T.is_failure(0.2, "released")
    assert not T.is_failure(0.6, "released")
    assert T.is_failure(0.9, "disputed")


def _vec_with_failures(n, age_days=0):
    v = T.new_vector()
    for i in range(n):
        v["failures"].append({"acp_job_id": i, "ts": T.iso(NOW - timedelta(days=age_days)),
                              "category": "research", "reason": "x"})
    return v


def test_status_thresholds():
    assert T.derive_status(_vec_with_failures(0), NOW) == C.STATUS_TRUSTED
    assert T.derive_status(_vec_with_failures(1), NOW) == C.STATUS_TRUSTED
    assert T.derive_status(_vec_with_failures(2), NOW) == C.STATUS_PROBATION
    assert T.derive_status(_vec_with_failures(3), NOW) == C.STATUS_BLACKLISTED


def test_failures_expire_after_ttl():
    v = _vec_with_failures(3, age_days=31)
    assert T.derive_status(v, NOW) == C.STATUS_TRUSTED
    v = _vec_with_failures(3, age_days=29)
    assert T.derive_status(v, NOW) == C.STATUS_BLACKLISTED


def test_apply_outcome_rewrites_dimensions_and_records_failure():
    v = T.new_vector()
    T.apply_outcome(v, {"acp_job_id": 7, "category": "research", "score": 0.2, "action": "disputed",
                        "latency_s": 300, "sla_s": 900, "quoted_price_usdc": 0.01,
                        "charged_price_usdc": 0.02, "refunded": True}, NOW)
    assert v["trust"]["spec_adherence"] == 0.2
    assert v["trust"]["latency"] == 1.0
    assert v["trust"]["price_drift"] == 0.0
    assert v["trust"]["refund_behavior"] == 1.0
    assert v["per_category_competence"]["research"] == 0.2
    assert v["sample_count"] == 1
    assert v["failures"][0]["acp_job_id"] == 7
    # refund not observed -> stays at prior
    v2 = T.new_vector()
    T.apply_outcome(v2, {"score": 0.9}, NOW)
    assert v2["trust"]["refund_behavior"] == C.PRIOR


def test_private_score_and_premium():
    v = T.new_vector()
    assert T.private_score(v, "research") == 0.5
    assert T.risk_premium(0.5) == 0.21
    assert T.risk_premium(0.65) == 0.0
    assert T.risk_premium(0.9) == 0.0
    assert T.risk_premium(0.1) == 0.5
    assert T.risk_premium(0.6, observed_max_drift=0.3) == round(0.07 + 0.3, 4)


def test_terms_table():
    assert T.terms_for(C.STATUS_BLACKLISTED, 0.9, 1.0)["max_job_usdc"] == 0.0
    p = T.terms_for(C.STATUS_PROBATION, 0.9, 1.0)
    assert p["max_job_usdc"] == 0.25 and p["staged"] and p["require_evaluator"] and p["retry_budget"] == 0
    u = T.terms_for(C.STATUS_UNKNOWN, 0.5, 1.0)
    assert u["max_job_usdc"] == 0.1 and u["staged"] and u["retry_budget"] == 1
    t = T.terms_for(C.STATUS_TRUSTED, 0.9, 1.0)
    assert t["max_job_usdc"] == 1.4 and not t["staged"] and not t["require_evaluator"] and t["retry_budget"] == 2
    t2 = T.terms_for(C.STATUS_TRUSTED, 0.7, 1.0)
    assert t2["staged"] and t2["require_evaluator"]


def test_keccak_known_vector():
    assert keccak256_hex(b"") == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert keccak256_hex(b"abc") == "0x4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"


def test_commitment_binds_chain_and_registry():
    a = commitment(8453, "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63", "0x" + "ab" * 20, 42, "specfail")
    b = commitment(84532, "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63", "0x" + "ab" * 20, 42, "specfail")
    c = commitment(8453, "0x" + "00" * 20, "0x" + "ab" * 20, 42, "specfail")
    assert a != b and a != c and len(a) == 66
