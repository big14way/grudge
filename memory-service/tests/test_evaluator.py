from grudge_memory.evaluator import DEFAULT_SPECS, evaluate

GOOD_RESEARCH = """# Summary
This report covers the topic in depth. """ + "word " * 160 + """
- Source: https://example.com/a
- Source: https://example.com/b
Risks: the main risk is data staleness.
"""


def test_good_delivery_passes():
    r = evaluate(DEFAULT_SPECS["research"], GOOD_RESEARCH)
    assert r["score"] == 1.0 and r["unmet"] == [] and r["notes"].startswith("specok")


def test_bad_delivery_fails_and_names_unmet():
    r = evaluate(DEFAULT_SPECS["research"], "too short, no sources")
    assert r["score"] < 0.5 and "sources" in r["unmet"] and r["notes"].startswith("specfail")


def test_empty_delivery():
    r = evaluate(DEFAULT_SPECS["writing"], None)
    assert r["score"] == 0.0 and r["criteria_met"] == 0


def test_json_keys_criterion():
    spec = {"criteria": [{"id": "j", "type": "json_keys", "value": ["a", "b"]}]}
    assert evaluate(spec, '{"a":1,"b":2}')["score"] == 1.0
    assert evaluate(spec, '{"a":1}')["score"] == 0.0
    assert evaluate(spec, "not json")["score"] == 0.0
