"""Social ingest — streams/polls posts into pf_social_raw. Raw only, no analysis
(the scoring job in runtime/feed does that), mirroring scan/news.py.

This is the ONE piece that needs a credential and is therefore a stub until one
is wired: set SOCIAL_X_BEARER (an X/Twitter API bearer token) and SOCIAL_X_RULES
(a comma-separated filter, e.g. "from:binance,$BTC,$ETH"). Without a token the
service refuses to run rather than invent data — a backtest built on fabricated
posts would be worthless.

normalize() and _upsert() are real and shaped for the feed pipeline, so wiring a
provider is just filling fetch_stream().

Run:  python3 -m runtime.scan.social            # loop
      python3 -m runtime.scan.social --once     # one pass, exit
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import core.env  # noqa: F401
from .. import pf_db

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BEARER = os.environ.get("SOCIAL_X_BEARER", "")
RULES = [r.strip() for r in os.environ.get("SOCIAL_X_RULES", "").split(",") if r.strip()]
POLL_SECONDS = 30


def normalize(post, source="x"):
    """Provider payload -> the one raw-event schema (pf_social_raw row)."""
    return {
        "event_id": f"{source}:{post['id']}",
        "source": source,
        "author_id": str(post.get("author_id") or ""),
        "author_handle": post.get("author_handle") or "",
        "text": post.get("text") or "",
        "lang": post.get("lang"),
        "url": post.get("url"),
        "created_at_ms": int(post["created_at_ms"]),
        "ingested_at_ms": int(time.time() * 1000),
        "raw": post.get("raw"),
    }


def fetch_stream():
    """Yield raw provider posts. STUB: wire an X filtered-stream / timeline poll
    here using BEARER + RULES. Must yield dicts with at least id, text,
    created_at_ms, author_handle. Left unimplemented on purpose — no creds, no
    data (never fabricate)."""
    raise NotImplementedError(
        "wire an X/social provider in fetch_stream() using SOCIAL_X_BEARER")


def _upsert(rows):
    req_body = json.dumps([pf_db.json_safe(r) for r in rows]).encode()
    import urllib.request
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_social_raw?on_conflict=event_id",
        data=req_body, method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def scan_once():
    rows, seen = [], set()
    for post in fetch_stream():
        row = normalize(post)
        if row["event_id"] in seen:
            continue
        seen.add(row["event_id"])
        rows.append(row)
    for i in range(0, len(rows), 200):
        _upsert(rows[i:i + 200])
    return len(rows)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    if not BEARER:
        sys.exit("SOCIAL_X_BEARER not set — social ingest needs a provider "
                 "credential; refusing to run (no fabricated data).")
    once = "--once" in argv
    while True:
        try:
            print(f"social_scan: upserted {scan_once()} posts")
        except NotImplementedError as e:
            sys.exit(str(e))
        except Exception as e:
            print(f"social_scan error: {e}", file=sys.stderr)
        if once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
