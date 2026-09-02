"""Deterministic spec evaluator.

Reads the REFERENCE spec for a job category and scores a delivery against its
acceptance criteria. Same spec, same delivery, same score, every session.
That is why the spec lives in memory and not in the broker's code.

Criterion shapes:
  {"id": "...", "type": "min_words", "value": 300}
  {"id": "...", "type": "max_words", "value": 2000}
  {"id": "...", "type": "contains", "value": "conclusion"}          # case-insensitive
  {"id": "...", "type": "contains_any", "value": ["http://", "https://"]}
  {"id": "...", "type": "regex", "value": "(?i)^#\\s"}
  {"id": "...", "type": "min_count", "value": 3, "pattern": "https?://"}
  {"id": "...", "type": "json_keys", "value": ["summary", "sources"]}
"""
from __future__ import annotations

import json
import re
from typing import Any


def _check(criterion: dict[str, Any], delivery: str) -> bool:
    t = criterion.get("type")
    v = criterion.get("value")
    if t == "min_words":
        return len(delivery.split()) >= int(v)
    if t == "max_words":
        return len(delivery.split()) <= int(v)
    if t == "contains":
        return str(v).lower() in delivery.lower()
    if t == "contains_any":
        low = delivery.lower()
        return any(str(x).lower() in low for x in v)
    if t == "regex":
        return re.search(str(v), delivery, re.MULTILINE) is not None
    if t == "min_count":
        return len(re.findall(str(criterion.get("pattern", "")), delivery)) >= int(v)
    if t == "json_keys":
        try:
            obj = json.loads(delivery)
        except (TypeError, ValueError):
            return False
        return isinstance(obj, dict) and all(k in obj for k in v)
    return False


def evaluate(spec: dict[str, Any], delivery: str | None) -> dict[str, Any]:
    criteria = spec.get("criteria", [])
    delivery = delivery or ""
    met, unmet = [], []
    for c in criteria:
        ok = bool(delivery.strip()) and _check(c, delivery)   # an empty delivery meets nothing
        (met if ok else unmet).append(c.get("id"))
    total = len(criteria)
    score = round(len(met) / total, 4) if total else 0.0
    return {
        "score": score,
        "criteria_met": len(met),
        "criteria_total": total,
        "met": met,
        "unmet": unmet,
        "notes": ("specok" if score >= 0.5 else "specfail")
                 + (f": unmet {', '.join(str(u) for u in unmet)}" if unmet else ""),
    }


DEFAULT_SPECS: dict[str, dict[str, Any]] = {
    "research": {
        "category": "research",
        "sla_seconds": 900,
        "base_size_usdc": 0.10,
        "criteria": [
            {"id": "length", "type": "min_words", "value": 150},
            {"id": "sources", "type": "min_count", "value": 2, "pattern": r"https?://"},
            {"id": "summary", "type": "contains", "value": "summary"},
            {"id": "risks", "type": "contains_any", "value": ["risk", "caveat", "limitation"]},
            {"id": "structure", "type": "regex", "value": r"(?m)^(#|\d+\.|-)\s"},
        ],
    },
    "writing": {
        "category": "writing",
        "sla_seconds": 600,
        "base_size_usdc": 0.05,
        "criteria": [
            {"id": "length", "type": "min_words", "value": 100},
            {"id": "not_bloated", "type": "max_words", "value": 800},
            {"id": "title", "type": "regex", "value": r"(?m)^#\s"},
            {"id": "cta", "type": "contains_any", "value": ["learn more", "get started", "try"]},
        ],
    },
}
