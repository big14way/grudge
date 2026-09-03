"""python -m grudge_memory  [--db PATH] [--port 7411]"""
from __future__ import annotations

import argparse
import os

from .server import serve
from .store import MemoryStore


def main() -> None:
    ap = argparse.ArgumentParser(prog="grudge-memory")
    ap.add_argument("--db", default=os.environ.get("GRUDGE_MEMORY_DB", "~/.sibyl-memory/grudge.db"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("GRUDGE_MEMORY_PORT", "7411")))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    store = MemoryStore(args.db)
    for tenant in ("broker-a", "broker-b"):
        store.seed_references(tenant)
    httpd = serve(store, args.host, args.port)
    tier = store._client.get_tier()
    print(f"[MEMORY] service  up on http://{args.host}:{args.port} db={store.db_path} "
          f"(single writer, WAL, busy_timeout 5000ms) sibyl tier={tier} "
          f"account={'activated ' + str(store.account)[:8] + '..' if store.account else 'not activated, run sibyl init'}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("[MEMORY] service  down", flush=True)


if __name__ == "__main__":
    main()
