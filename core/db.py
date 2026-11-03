"""Supabase reader — read-only access to the product database.

Via the REST API with the public anon key (same RLS the web app uses). The DB
is the single source of truth for data the engine needs. Config from env:

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

from . import universe as _uni
from . import marketdata as _md

from . import env as _env  # noqa: F401 — loads .env
URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_ANON_KEY", "")
_TTL = 300
_cache = {}

# instruments a rule-universe resolves against: the live Binance perp set +
# 24h volume. On fetch failure, universe_symbols returns None and the caller
# treats the rule-universe as unresolved. Tests/offline override with
# set_provider(_md.from_bn_coverage). List-universes store their coins instead.
_PROVIDER = _md.from_binance


def set_provider(fn):
    global _PROVIDER
    _PROVIDER = fn


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
    """slug -> {symbol: binance_symbol} from pf_universes / pf_instruments.
    None if the DB is off, the slug is unknown, or a read fails (caller
    falls back)."""
    if not enabled():
        return None
    try:
        return _cached(f"uni:{slug}", lambda: _resolve(slug))
    except Exception:
        return None


def coin_symbols(tickers):
    """[ticker, ...] -> {ticker: binance_symbol} from pf_instruments. Used to
    resolve a cross-asset operand's symbol (e.g. "BTC") to a fetchable exchange
    symbol, the same table universes resolve against. {} if the DB is off or a
    read fails (the caller treats an unresolved symbol as no data)."""
    tickers = [t for t in dict.fromkeys(tickers) if t]
    if not tickers or not enabled():
        return {}
    try:
        coins = _get("pf_instruments",
                     {"symbol": f"in.({','.join(tickers)})",
                      "select": "symbol,binance_symbol"})
        return {c["symbol"]: c["binance_symbol"] for c in coins}
    except Exception:
        return {}


def _resolve(slug):
    unis = _get("pf_universes",
                {"slug": f"eq.{slug}", "select": "id,definition,market"})
    if not unis:
        return None
    u = unis[0]
    mkt = u.get("market")
    defn = u.get("definition") or {}
    # rule-universe: resolve the rule against the live tradeable set, so it
    # stays current (e.g. "top 100 by volume") — no coins are stored.
    if defn.get("rule"):
        return _uni.resolve(defn, _PROVIDER()) or None
    # list-universe (incl. a user's hand-picked set): the instruments are stored
    # in pf_universe_instruments -> pf_instruments.
    rows = _get("pf_universe_instruments",
                {"universe_id": f"eq.{u['id']}", "select": "instrument_symbol"})
    syms = [r["instrument_symbol"] for r in rows]
    if not syms:
        return None
    params = {"symbol": f"in.({','.join(syms)})",
              "select": "symbol,binance_symbol,market"}
    if mkt:
        params["market"] = f"eq.{mkt}"
    coins = _get("pf_instruments", params)
    # Containment: a universe may only trade instruments in its own market. A
    # coin whose market differs from the universe's is dropped — the engine-side
    # backstop against a mislabeled universe (e.g. an fx_spot universe seeded
    # with crypto coins, which must resolve to nothing, not trade crypto).
    return {c["symbol"]: c["binance_symbol"] for c in coins
            if not mkt or c.get("market") == mkt}
