from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SIBYL_MEMORY_TELEMETRY"] = "0"
os.environ["GRUDGE_SIBYL_CREDENTIALS"] = "/nonexistent/credentials.json"   # tests never touch a real account

from grudge_memory.store import MemoryStore  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def logs() -> list[str]:
    return []


@pytest.fixture
def store(tmp_path, clock, logs) -> MemoryStore:
    s = MemoryStore(str(tmp_path / "mem.db"), now_fn=clock, log=logs.append)
    s.seed_references("broker-a")
    s.seed_references("broker-b")
    return s


GOOD = "0x1111111111111111111111111111111111111111"
BURN = "0x2222222222222222222222222222222222222222"
NEWB = "0x3333333333333333333333333333333333333333"


def outcome(provider: str, job_id: int, score: float, *, category="research", action=None,
            quoted=0.01, charged=0.01, latency=300, sla=900, refunded=None, public=None):
    return {
        "provider": provider, "acp_job_id": job_id, "category": category, "score": score,
        "action": action or ("released" if score >= 0.5 else "disputed"),
        "reason": "spec unmet" if score < 0.5 else "ok",
        "quoted_price_usdc": quoted, "charged_price_usdc": charged,
        "latency_s": latency, "sla_s": sla, "refunded": refunded,
        "chain_id": 84532, "broker_wallet": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        "public_score": public,
    }
