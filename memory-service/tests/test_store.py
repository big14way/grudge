"""Behavioural tests for the memory store: promotion, in-place rewrite, status
transitions, decay on read, the hire decision, consortium refusal, multi-record."""
import json
import sqlite3

from grudge_memory import config as C
from conftest import BURN, GOOD, NEWB, outcome

A, B = "broker-a", "broker-b"


def _entity_rows(store, tenant, name):
    conn = sqlite3.connect(store.db_path)
    n = conn.execute("SELECT COUNT(*) FROM entities WHERE tenant_id=? AND category='counterparty' AND name=?",
                     (tenant, name)).fetchone()[0]
    conn.close()
    return n


def test_new_counterparty_stays_in_journal_until_three_samples(store, logs):
    r1 = store.record_outcome(A, outcome(NEWB, 1, 0.9))
    r2 = store.record_outcome(A, outcome(NEWB, 2, 0.8))
    assert not r1["promoted"] and not r2["promoted"]
    assert r2["status"] == C.STATUS_UNKNOWN
    assert _entity_rows(store, A, NEWB) == 0
    assert any("stays journal-only" in l for l in logs)
    r3 = store.record_outcome(A, outcome(NEWB, 3, 0.85))
    assert r3["promoted"] and r3["status"] == C.STATUS_TRUSTED
    assert r3["vector"]["sample_count"] == 3
    assert r3["vector"]["promoted_from"] == "journal"
    assert _entity_rows(store, A, NEWB) == 1
    assert any("PROMOTE journal -> entity" in l for l in logs)


def test_two_failures_promote_early_into_probation(store):
    store.record_outcome(A, outcome(BURN, 10, 0.2, refunded=True))
    r = store.record_outcome(A, outcome(BURN, 11, 0.1, refunded=True))
    assert r["promoted"] and r["status"] == C.STATUS_PROBATION
    assert [f["acp_job_id"] for f in r["vector"]["failures"]] == [10, 11]
    assert r["vector"]["trust"]["refund_behavior"] == 1.0   # refund observations survive the journal -> entity rebuild


def test_trust_vector_rewritten_in_place_never_appended(store, logs):
    for i in range(6):
        store.record_outcome(A, outcome(GOOD, 100 + i, 0.9))
    assert _entity_rows(store, A, GOOD) == 1
    vec, status = store.get_counterparty(A, GOOD)
    assert vec["sample_count"] == 6 and status == C.STATUS_TRUSTED
    assert sum("REWRITTEN IN PLACE" in l for l in logs) == 3   # samples 4,5,6 after promotion at 3


def test_third_failure_blacklists(store):
    store.record_outcome(A, outcome(BURN, 1, 0.2))
    store.record_outcome(A, outcome(BURN, 2, 0.2))
    r = store.record_outcome(A, outcome(BURN, 3, 0.2))
    assert r["status"] == C.STATUS_BLACKLISTED
    assert store.list_counterparties(A, status=C.STATUS_BLACKLISTED)[0]["address"] == BURN


def test_decay_on_read_returns_blacklisted_to_probation_then_trusted(store, clock, logs):
    store.record_outcome(A, outcome(BURN, 1, 0.2))
    clock.advance(days=2)
    store.record_outcome(A, outcome(BURN, 2, 0.2))
    clock.advance(days=2)
    store.record_outcome(A, outcome(BURN, 3, 0.2))
    assert store.get_counterparty(A, BURN)[1] == C.STATUS_BLACKLISTED
    clock.advance(days=27)   # first failure is now 31 days old
    vec, status = store.get_counterparty(A, BURN)
    assert status == C.STATUS_PROBATION
    assert any("blacklisted -> probation" in l for l in logs)
    assert vec["trust"]["spec_adherence"] > 0.2   # decayed toward the 0.5 prior
    clock.advance(days=4)    # all three older than 30 days
    assert store.get_counterparty(A, BURN)[1] == C.STATUS_TRUSTED
    assert _entity_rows(store, A, BURN) == 1


def test_decide_passes_over_top_public_score_and_names_the_job(store, clock):
    # BURN has the best public score but burned us twice in research.
    store.record_outcome(A, outcome(BURN, 501, 0.2, public={"score": 0.97}))
    clock.advance(hours=1)
    store.record_outcome(A, outcome(BURN, 502, 0.1, public={"score": 0.97}))
    for i in range(3):
        store.record_outcome(A, outcome(GOOD, 600 + i, 0.9, public={"score": 0.70}))
    d = store.decide(A, {"category": "research", "budget_usdc": 0.02},
                     [{"address": BURN, "public_score": 0.97, "quoted_price_usdc": 0.01},
                      {"address": GOOD, "public_score": 0.70, "quoted_price_usdc": 0.01},
                      {"address": NEWB, "public_score": 0.80, "quoted_price_usdc": 0.01}])
    assert d["chosen"]["address"] == GOOD
    burn = next(r for r in d["ranked"] if r["address"] == BURN)
    assert burn["verdict"] == "refuse"
    assert "502" in burn["reason"] and "2026-09-02T13:00:00Z" in burn["reason"]
    assert burn["terms"]["dispute_window_s"] == C.DISPUTE_WINDOW_BASE_S * C.DISPUTE_WINDOW_TROUBLE_MULT
    newb = next(r for r in d["ranked"] if r["address"] == NEWB)
    assert newb["status"] == C.STATUS_UNKNOWN and newb["terms"]["staged"] and newb["terms"]["require_evaluator"]
    assert newb["risk_premium"] == 0.21
    good = d["chosen"]
    assert good["private_score"] > newb["private_score"]
    assert good["terms"]["retry_budget"] == 2
    # the counterfactual is stated: a memoryless broker takes the top public score at flat terms
    cf = d["counterfactual"]
    assert cf["address"] == BURN and cf["memory_says"] == C.STATUS_PROBATION and cf["live_failures"] == 2
    assert cf["delta"]["provider_changed"] is True and cf["terms"]["require_evaluator"] is False


def test_probation_provider_allowed_in_other_category_at_probation_terms(store):
    store.record_outcome(A, outcome(BURN, 1, 0.2, category="research"))
    store.record_outcome(A, outcome(BURN, 2, 0.2, category="research"))
    d = store.decide(A, {"category": "writing", "budget_usdc": 0.05},
                     [{"address": BURN, "quoted_price_usdc": 0.01}])
    r = d["ranked"][0]
    assert r["status"] == C.STATUS_PROBATION
    assert r["terms"]["max_job_usdc"] == round(0.05 * C.SIZE_CAP_PROBATION, 6)
    assert r["terms"]["retry_budget"] == 0


def test_price_refusal_from_private_premium(store):
    for i in range(3):
        store.record_outcome(A, outcome(GOOD, i, 0.55, quoted=0.01, charged=0.02))  # mediocre + overcharges
    d = store.decide(A, {"category": "research", "budget_usdc": 0.011},
                     [{"address": GOOD, "quoted_price_usdc": 0.01}])
    r = d["ranked"][0]
    assert r["risk_premium"] > 0.21           # drift evidence from the journal raised it
    assert r["verdict"] == "refuse" and r["reason"].startswith("price")


def test_size_refusal(store):
    d = store.decide(A, {"category": "research", "budget_usdc": 1.0},
                     [{"address": NEWB, "quoted_price_usdc": 0.5}])
    assert d["ranked"][0]["reason"].startswith("size")   # unknown cap = 10% of 0.10 base


def test_consortium_signal_is_redacted_and_broker_b_refuses(store, logs):
    store.record_outcome(A, outcome(BURN, 1, 0.2, quoted=0.01, charged=0.01))
    store.record_outcome(A, outcome(BURN, 2, 0.2, quoted=0.01, charged=0.01))
    sig = store.consortium_signal(BURN)
    assert sig["live_failures"] == 2 and sig["reporters"] == [A] and sig["status"] == C.STATUS_PROBATION
    assert sig["categories_failed"] == ["research"]
    dumped = json.dumps(sig)
    for forbidden in ("price", "0.01", "acp_job_id", "unmet", "notes", "spec unmet"):
        assert forbidden not in dumped
    assert all(c.startswith("0x") and len(c) == 66 for c in sig["commitments"])
    # broker B never met BURN: its own tenant is empty, it reads the consortium and refuses
    assert store.get_counterparty(B, BURN) == (None, C.STATUS_UNKNOWN)
    d = store.decide(B, {"category": "research", "budget_usdc": 0.02},
                     [{"address": BURN, "public_score": 0.97, "quoted_price_usdc": 0.01},
                      {"address": NEWB, "public_score": 0.5, "quoted_price_usdc": 0.01}])
    burn = next(r for r in d["ranked"] if r["address"] == BURN)
    assert burn["verdict"] == "refuse" and burn["reason"].startswith("consortium")
    assert d["chosen"]["address"] == NEWB
    # broker A's private detail never left tenant broker-a
    assert store.journal_for(B, BURN) == []


def test_hot_state_negotiation_cleared_on_outcome(store):
    store.mark_inflight(A, 77, {"stage": "budget.set", "budget": 0.01})
    assert store.get_state(A, "inflight") == {"jobs": [77]}
    assert store.get_state(A, "negotiation:77")["stage"] == "budget.set"
    store.record_outcome(A, outcome(GOOD, 77, 0.9))
    assert store.get_state(A, "inflight") == {"jobs": []}
    assert store.get_state(A, "negotiation:77")["closed"] is True


def test_reference_spec_drives_evaluation_consistently(store):
    r = store.evaluate_delivery(A, "research", "short")
    assert r["score"] < 0.5 and r["sla_seconds"] == 1800
    store.set_spec(A, "research", {"criteria": [{"id": "any", "type": "min_words", "value": 1}],
                                   "sla_seconds": 10, "base_size_usdc": 0.1})
    assert store.evaluate_delivery(A, "research", "short")["score"] == 1.0


def test_multi_record_query_spans_linked_records(store, logs):
    store.record_outcome(A, outcome(BURN, 1, 0.2, quoted=0.01, charged=0.02))   # failed + overcharged
    store.record_outcome(A, outcome(GOOD, 2, 0.9, quoted=0.01, charged=0.02))   # overcharged only
    store.record_outcome(A, outcome(NEWB, 3, 0.2, quoted=0.01, charged=0.01))   # failed only
    res = store.multi_query(A, "research specfail overcharged")
    assert res["providers"] == [BURN]
    assert any("multi_record_search" in l and "stage1 retrieve -> stage2 verify" in l for l in logs)


def test_tenants_are_isolated(store):
    store.record_outcome(A, outcome(GOOD, 1, 0.9))
    assert store.journal_for(B, GOOD) == []
    assert store.list_counterparties(B) == []
