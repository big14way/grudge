import json
import threading
import urllib.request

import pytest

from grudge_memory.server import serve
from conftest import BURN, GOOD, outcome


@pytest.fixture
def api(store):
    httpd = serve(store, "127.0.0.1", 0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    def call(method, path, body=None, tenant="broker-a"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Grudge-Tenant": tenant})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    call.port = port
    yield call
    httpd.shutdown()


def test_health_and_roundtrip(api):
    assert api("GET", "/health")[1]["ok"] is True
    s, r = api("POST", "/evaluate", {"category": "research", "delivery": "short"})
    assert s == 200 and r["score"] < 0.5
    for i in range(2):
        s, r = api("POST", "/outcome", outcome(BURN, i, 0.2))
    assert r["status"] == "probation"
    s, r = api("GET", f"/counterparty/{BURN}")
    assert r["status"] == "probation" and r["vector"]["sample_count"] == 2
    s, r = api("POST", "/decide", {"job": {"category": "research", "budget_usdc": 0.02},
                                   "candidates": [{"address": BURN, "public_score": 0.99, "quoted_price_usdc": 0.01},
                                                  {"address": GOOD, "public_score": 0.5, "quoted_price_usdc": 0.01}]})
    assert r["chosen"]["address"] == GOOD
    # broker B via header sees the consortium only
    s, r = api("GET", f"/counterparty/{BURN}", tenant="broker-b")
    assert r["status"] == "unknown"
    s, r = api("GET", f"/consortium/{BURN}")
    assert r["signal"]["live_failures"] == 2
    s, r = api("GET", "/events?limit=5")
    assert len(r["events"]) == 2
    s, r = api("POST", "/query/multi", {"query": "research specfail"})
    assert s == 200 and BURN in r["providers"]


def test_bad_request(api):
    s, r = api("POST", "/decide", {"job": {"category": "research"}})
    assert s == 400
    s, r = api("GET", "/nope")
    assert s == 404


def test_viewer_is_quiet(api, store):
    for i in range(2):
        api("POST", "/outcome", outcome(BURN, 50 + i, 0.2))
    reads_before, writes_before = store.reads, store.writes
    s, snap = api("GET", "/snapshot")
    assert s == 200 and snap["tenants"]["broker-a"]["counterparties"][0]["status"] == "probation"
    assert snap["consortium"][0]["live_failures"] == 2
    s, log = api("GET", "/log?after=0")
    assert log["lines"] and any("PROMOTE" in l["line"] for l in log["lines"])
    assert (store.reads, store.writes) == (reads_before, writes_before)   # viewer never counts as memory traffic
    import urllib.request
    html = urllib.request.urlopen(f"http://127.0.0.1:{api.port}/ui").read().decode()
    assert "MEMORY LAYER GONE" in html
