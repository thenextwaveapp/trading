"""Market discovery feed — the engine fetches the live market and stores it.

Runs on the non-US VPS (Binance returns 451 to US IPs). Each pass pulls the 24h
ticker, keeps the most-traded USDT perps, and upserts pf_market_snapshot. The
web reads that table for the discovery board. Engine writes, web renders.

Run:  python3 -m runtime.market_scan            # loop
      python3 -m runtime.market_scan --once     # one pass, exit
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.env  # noqa: F401  (loads .env)
from . import pf_db

TICKER = "https://fapi.binance.com/fapi/v1/ticker/24hr"
CG_MARKETS = ("https://api.coingecko.com/api/v3/coins/markets"
              "?vs_currency=usd&order=market_cap_desc&per_page=250&page=")
TOP_N = 300
POLL_SECONDS = 60


CG_KEY = os.environ.get("CG_API_KEY", "")
CG_TTL = 600  # names/market-caps move slowly; refetch at most every 10 min
_cg_cache = {"t": 0.0, "map": {}}


def fetch_coingecko():
    """{UPPER_SYMBOL: {name, logo, market_cap, rank, supply, ath}} for the top
    coins by market cap. First match per symbol wins (highest cap), so a ticker
    collision resolves to the real coin. Cached (CoinGecko's free tier rate-
    limits datacenter IPs hard); set CG_API_KEY for a free demo key. Keeps the
    last good map on failure."""
    import time as _t
    if _cg_cache["map"] and _t.time() - _cg_cache["t"] < CG_TTL:
        return _cg_cache["map"]
    headers = {"User-Agent": "paperfleet"}
    if CG_KEY:
        headers["x-cg-demo-api-key"] = CG_KEY
    out = {}
    for page in (1, 2):
        req = urllib.request.Request(CG_MARKETS + str(page), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                rows = json.loads(r.read())
        except Exception:
            break
        for c in rows:
            sym = (c.get("symbol") or "").upper()
            if not sym or sym in out:
                continue
            out[sym] = {
                "name": c.get("name"), "logo": c.get("image"),
                "market_cap": c.get("market_cap"),
                "market_cap_rank": c.get("market_cap_rank"),
                "circ_supply": c.get("circulating_supply"),
                "ath": c.get("ath"),
            }
    if out:
        _cg_cache["t"], _cg_cache["map"] = _t.time(), out
    return out or _cg_cache["map"]
URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def fetch_24h():
    req = urllib.request.Request(TICKER, headers={"User-Agent": "paperfleet"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _upsert(rows):
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_market_snapshot?on_conflict=symbol",
        data=json.dumps(rows).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def scan_once():
    now = datetime.now(timezone.utc).isoformat()
    cg = fetch_coingecko()
    perps = [d for d in fetch_24h() if d.get("symbol", "").endswith("USDT")]
    perps.sort(key=lambda d: float(d.get("quoteVolume", 0) or 0), reverse=True)
    rows = []
    for d in perps[:TOP_N]:
        sym = d["symbol"]
        try:
            base = sym[:-4]
            row = {
                "symbol": sym, "base": base, "market": "crypto",
                "price": float(d["lastPrice"]),
                "change_pct": float(d["priceChangePercent"]),
                "quote_volume": float(d["quoteVolume"]),
                "high": float(d["highPrice"]), "low": float(d["lowPrice"]),
                "trades": int(d.get("count", 0)), "updated_at": now,
            }
            # strip Binance's numeric multiplier prefix (1000PEPE -> PEPE) to
            # match CoinGecko's symbol.
            cg_key = base.lstrip("0123456789") or base
            if cg_key in cg:
                row.update(cg[cg_key])
            rows.append(row)
        except (KeyError, ValueError, TypeError):
            continue
    for i in range(0, len(rows), 200):
        _upsert(rows[i:i + 200])
    return len(rows)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        try:
            n = scan_once()
            print(f"market_scan: upserted {n} instruments")
        except Exception as e:
            print(f"market_scan error: {e}", file=sys.stderr)
        if once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
