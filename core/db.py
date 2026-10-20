"""Supabase reader — the engine's window into the product database.

Read-only, via the REST API with the public anon key (same RLS the web app
uses). This is what makes the DB the single source of truth for data the
engine needs — universes now, live bots next (#2). Config from env:

    SUPABASE_URL        e.g. https://<ref>.supabase.co
    SUPABASE_ANON_KEY   the public anon/publishable key

If unset or unreachable, callers fall back to local files. Results are cached
(5 min) so a backtest doesn't hit the DB every call.
"""
import json
import os
import time
import urllib.parse
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_ANON_KEY", "")
_TTL = 300
_cache = {}


def enabled():
    return bool(URL and KEY)


def _get(path, params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{URL}/rest/v1/{path}?{q}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _cached(key, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def universe_symbols(slug):
    """slug -> {coin_symbol: binance_symbol} from pf_universes / coins /
    pf_coins. None if the DB is off, the slug is unknown, or a read fails
    (caller falls back)."""
    if not enabled():
        return None
    try:
        return _cached(f"uni:{slug}", lambda: _resolve(slug))
    except Exception:
        return None


def _resolve(slug):
    unis = _get("pf_universes", {"slug": f"eq.{slug}", "select": "id"})
    if not unis:
        return None
    uid = unis[0]["id"]
    rows = _get("pf_universe_coins",
                {"universe_id": f"eq.{uid}", "select": "coin_symbol"})
    syms = [r["coin_symbol"] for r in rows]
    if not syms:
        return None
    coins = _get("pf_coins",
                 {"symbol": f"in.({','.join(syms)})",
                  "select": "symbol,binance_symbol"})
    return {c["symbol"]: c["binance_symbol"] for c in coins}
