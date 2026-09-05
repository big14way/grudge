"""Localhost HTTP front for the MemoryStore. Stdlib only.

The Node brokers are clients of this process. If this process is not running
the brokers cannot rank, price or set terms and exit. scripts/deletion_test.sh
proves that.

Routes (JSON in, JSON out). Tenant comes from the X-Grudge-Tenant header or a
"tenant" field in the body; default broker-a.
  GET  /health
  GET  /stats
  POST /decide          {job, candidates}
  POST /evaluate        {category, delivery}
  POST /outcome         {provider, acp_job_id, category, score, action, ...}
  POST /inflight        {acp_job_id, negotiation}
  GET  /counterparty/<address>
  GET  /counterparties?status=
  GET  /journal/<address>
  GET  /events?limit=
  GET  /consortium/<address>
  GET  /spec/<category>     PUT /spec/<category>
  GET  /state/<key>         PUT /state/<key>
  POST /query/multi     {query}
  GET  /                landing page (what GRUDGE is, how it works, try a decision)
  GET  /ui              thin live viewer (reads bypass the memory op counters)
  GET  /snapshot        viewer data
  GET  /log?after=N     [MEMORY] log lines after sequence N
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .store import MemoryStore

DEFAULT_TENANT = "broker-a"


def make_handler(store: MemoryStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "grudge-memory/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet default access log
            pass

        # ---- helpers
        def _json(self, code: int, obj: Any) -> None:
            data = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw) if raw else {}

        def _tenant(self, body: dict[str, Any] | None = None) -> str:
            return (self.headers.get("X-Grudge-Tenant") or (body or {}).get("tenant") or DEFAULT_TENANT)

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                body = self._body() if method in ("POST", "PUT") else {}
                tenant = self._tenant(body)
                result = self._dispatch(method, parts, qs, body, tenant)
                if result is None:
                    self._json(404, {"error": "not found", "path": url.path})
                else:
                    self._json(200, result)
            except (KeyError, ValueError) as e:
                self._json(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def _dispatch(self, m: str, p: list[str], qs: dict[str, str], body: dict[str, Any], tenant: str) -> Any:
            if m == "GET" and p == ["health"]:
                return {"ok": True, "service": "grudge-memory", "db": store.db_path}
            if m == "GET" and p == ["stats"]:
                return store.stats()
            if m == "GET" and p == ["snapshot"]:
                return store.snapshot()
            if m == "GET" and p == ["log"]:
                return {"lines": store.log_after(int(qs.get("after", 0)))}
            if m == "POST" and p == ["decide"]:
                return store.decide(tenant, body["job"], body["candidates"])
            if m == "POST" and p == ["evaluate"]:
                return store.evaluate_delivery(tenant, body["category"], body.get("delivery"))
            if m == "POST" and p == ["outcome"]:
                return store.record_outcome(tenant, body)
            if m == "POST" and p == ["inflight"]:
                store.mark_inflight(tenant, body["acp_job_id"], body.get("negotiation") or {})
                return {"ok": True}
            if m == "GET" and len(p) == 2 and p[0] == "counterparty":
                vec, status = store.get_counterparty(tenant, p[1])
                return {"address": p[1].lower(), "status": status, "vector": vec}
            if m == "GET" and p == ["counterparties"]:
                return {"counterparties": store.list_counterparties(tenant, qs.get("status"))}
            if m == "GET" and len(p) == 2 and p[0] == "journal":
                return {"events": store.journal_for(tenant, p[1])}
            if m == "GET" and p == ["events"]:
                return {"events": store.recent_events(tenant, limit=int(qs.get("limit", 50)))}
            if m == "GET" and len(p) == 2 and p[0] == "consortium":
                return {"address": p[1].lower(), "signal": store.consortium_signal(p[1])}
            if len(p) == 2 and p[0] == "spec":
                if m == "GET":
                    return {"category": p[1], "spec": store.get_spec(tenant, p[1])}
                if m == "PUT":
                    store.set_spec(tenant, p[1], body)
                    return {"ok": True}
            if len(p) == 2 and p[0] == "state":
                if m == "GET":
                    return {"key": p[1], "body": store.get_state(tenant, p[1])}
                if m == "PUT":
                    store.set_state(tenant, p[1], body)
                    return {"ok": True}
            if m == "POST" and p == ["query", "multi"]:
                return store.multi_query(tenant, body["query"], limit=int(body.get("limit", 10)))
            return None

        def do_GET(self) -> None:
            page = {"/": "landing.html", "/index.html": "landing.html", "/ui": "ui.html", "/ui/": "ui.html"}.get(urlparse(self.path).path)
            if page:
                data = (Path(__file__).parent / page).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._route("GET")

        def do_POST(self) -> None:
            self._route("POST")

        def do_PUT(self) -> None:
            self._route("PUT")

    return Handler


def serve(store: MemoryStore, host: str = "127.0.0.1", port: int = 7411) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    httpd.daemon_threads = True
    return httpd
