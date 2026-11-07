"""Feed scoring service: raw events -> pf_feed_score.

Reads recent raw events (pf_news headlines + pf_social_raw posts), resolves each
to instruments, scores it, aggregates onto the bar grid, and upserts the derived
per-(instrument, kind, bar-close) series the engine reads via the aux path.

Raw tables are never mutated — this writes a recomputable view. Re-running with
a better scorer or decay just rewrites pf_feed_score.

Run:  python3 -m runtime.feed.service            # loop
      python3 -m runtime.feed.service --once     # one pass, exit
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import core.env  # noqa: F401
from .. import pf_db
from . import aggregate as agg
from .resolve import resolve
from .score import score_event

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
M15 = 900_000
POLL_SECONDS = 60
LOOKBACK_MS = 6 * 60 * 60 * 1000          # score the last 6h of events each pass
HALF_LIFE_S = int(os.environ.get("FEED_HALFLIFE_S", "300"))


def _iso_to_ms(s):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _credibility():
    """source_key -> prior [0,1] from pf_feed_sources (default 0.5)."""
    rows = pf_db.get("pf_feed_sources", "select=source_key,credibility") or []
    table = {r["source_key"]: r.get("credibility", 0.5) for r in rows}
    return lambda k: table.get(k, 0.5)


def _known_symbols():
    rows = pf_db.get("pf_instruments", "select=symbol") or []
    return {r["symbol"] for r in rows} or None


def _raw_events(since_ms):
    """Normalized events from both raw sources since `since_ms`."""
    out = []
    for r in pf_db.get("pf_social_raw",
                       f"select=event_id,source,author_handle,text,created_at_ms"
                       f"&created_at_ms=gte.{since_ms}") or []:
        out.append({"id": r["event_id"], "t_ms": r["created_at_ms"],
                    "text": r.get("text", ""),
                    "source_key": f"{r.get('source','x')}:{r.get('author_handle','')}"})
    for r in pf_db.get("pf_news", "select=url,title,source,published_at"
                                  "&order=published_at.desc&limit=200") or []:
        t = _iso_to_ms(r.get("published_at") or "")
        if t is None or t < since_ms:
            continue
        out.append({"id": r["url"], "t_ms": t, "text": r.get("title", ""),
                    "source_key": f"news:{r.get('source','')}", "kind": "news"})
    return out


def _bar_grid(events):
    if not events:
        return []
    lo = min(e["t_ms"] for e in events) // M15 * M15 + M15
    hi = max(e["t_ms"] for e in events) // M15 * M15 + M15
    return list(range(lo, hi + M15, M15))


def scan_once():
    cred = _credibility()
    known = _known_symbols()
    now_ms = int(time.time() * 1000)
    raw = _raw_events(now_ms - LOOKBACK_MS)
    scored = []
    for ev in raw:
        s = score_event(ev["text"], ev["source_key"], cred)
        if s["magnitude"] == 0.0:
            continue                                   # no signal in the text
        for inst, rconf in resolve(ev["text"], known):
            scored.append({"instrument": inst, "t_ms": ev["t_ms"],
                           "direction": s["direction"], "magnitude": s["magnitude"],
                           "class_conf": s["class_conf"], "source_conf": s["source_conf"],
                           "resolution_conf": rconf, "_kind": ev.get("kind", "social")})
    grid = _bar_grid(scored)
    rows = []
    for kind in ("social", "news"):
        evs = [e for e in scored if e["_kind"] == kind]
        rows += agg.aggregate(evs, grid, half_life_s=HALF_LIFE_S, kind=kind)
    db_rows = [{k: v for k, v in r.items() if k not in ("t", "event_ts")} | {
        "scored_at_ms": now_ms, "event_id": None, "event_text": None,
        "event_created_ms": r.get("event_ts")} for r in rows]
    for i in range(0, len(db_rows), 200):
        _upsert(db_rows[i:i + 200])
    return len(db_rows)


def _upsert(rows):
    """Upsert the derived series on its (instrument, kind, t_close) key — a
    re-score of the same bar replaces that bar's row, never appends."""
    body = json.dumps([pf_db.json_safe(r) for r in rows]).encode()
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_feed_score?on_conflict=instrument,kind,t_close",
        data=body, method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        try:
            print(f"feed_score: upserted {scan_once()} rows")
        except Exception as e:
            print(f"feed_score error: {e}", file=sys.stderr)
        if once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
