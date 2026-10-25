"""The engine service — API-first.

Everything the product needs from the engine is a plain function in ENDPOINTS
(validate / backtest / checks / catalog / health). The HTTP server below is a
thin adapter over them; an MCP server or a direct Python/API caller would be
the same thin adapter over the same functions.

Data: endpoints accept candles inline — `candles` (one series) or
`candles_by_ticker` ({ticker: [...]}) — for offline deterministic compute. If
given `symbols` + `interval`/`limit` instead, the service fetches closed
candles from Binance.

Run:  python3 -m core.service [--port 8099]
Test: curl -s localhost:8099/v1/healthz
"""
import csv
import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .strategy import parse, StrategyError
from .backtest import backtest, backtest_universe
from .checks import run_checks
from .conditions import conditions_breakdown
from .mapping import variant_to_spec
from . import db
from . import presets as _presets
from .export_catalog import build as build_catalog

BINANCE = "https://fapi.binance.com/fapi/v1/klines"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY_MS = 86_400_000

# ---- data ----
MAX_SYMBOLS = 60        # safety cap
MAX_BARS = 200_000      # per-symbol safety cap when paging Binance
_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": DAY_MS}


def _interval_ms(interval):
    try:
        return int(interval[:-1]) * _UNIT_MS[interval[-1]]
    except (KeyError, ValueError, IndexError):
        return 900_000


def _iso_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _fetch_page(symbol, interval, limit, start, end):
    url = (f"{BINANCE}?symbol={symbol}&interval={interval}"
           f"&limit={min(int(limit), 1500)}")
    if start:
        url += f"&startTime={int(start)}"
    if end:
        url += f"&endTime={int(end)}"
    with urllib.request.urlopen(url, timeout=25) as r:
        rows = json.loads(r.read())
    now = int(time.time() * 1000)
    return [dict(t=int(x[0]), o=float(x[1]), h=float(x[2]), l=float(x[3]),
                 c=float(x[4]), v=float(x[5]))
            for x in rows if int(x[6]) <= now]


def fetch_candles(symbol, interval="15m", limit=1500, start=None, end=None):
    """Closed candles from Binance. With a `start` we page forward 1,500 bars
    at a time so a multi-year window is possible; without one this is the
    original single-request path."""
    if start is None:
        return _fetch_page(symbol, interval, limit, start, end)

    step = _interval_ms(interval)
    out, cursor = [], int(start)
    while True:
        batch = _fetch_page(symbol, interval, 1500, cursor, end)
        if not batch:
            break
        out.extend(batch)
        if len(out) >= MAX_BARS or len(batch) < 1500:
            break
        nxt = batch[-1]["t"] + step
        if nxt <= cursor or (end and nxt > int(end)):
            break
        cursor = nxt
    return out[:MAX_BARS]


def _cache_path(interval):
    base = os.environ.get("PAPERFLEET_CANDLE_CACHE")
    path = (os.path.join(base, f"bn_candles_{interval}.csv.gz") if base
            else os.path.join(_ROOT, "lab", "bn", f"bn_candles_{interval}.csv.gz"))
    return path if os.path.exists(path) else None


def _read_cache(symbols, interval, start, end):
    """Read the local bn/ pull for just the requested symbols.

    -> ({ticker: candles}, seen_symbols). `seen_symbols` is every requested
    symbol present in the cache file, even if it has no bars inside the
    window, so we don't re-fetch a delisted coin from Binance.
    """
    path = _cache_path(interval)
    if not path:
        return {}, set()
    want = {sym: tk for tk, sym in symbols.items()}
    out = {tk: [] for tk in symbols}
    seen = set()
    with gzip.open(path, "rt", newline="") as f:
        for x in csv.DictReader(f):
            sym = x.get("symbol")
            if sym not in want:
                continue
            seen.add(sym)
            t = int(x["t"])
            if start and t < int(start):
                continue
            if end and t > int(end):
                continue
            out[want[sym]].append({
                "t": t, "o": float(x["o"]), "h": float(x["h"]),
                "l": float(x["l"]), "c": float(x["c"]), "v": float(x["v"]),
            })
    return {tk: rows for tk, rows in out.items() if rows}, seen


def _window(body):
    win = body.get("window") or {}
    start, end = win.get("start"), win.get("end")
    days = body.get("days")
    if start is None and days:
        end = int(end or time.time() * 1000)
        start = int(end - float(days) * DAY_MS)
    return (int(start) if start else None, int(end) if end else None)


def _resolve_universe(body):
    """-> ({ticker: candles}, meta). Resolves a universe slug (fleet-60 /
    majors), `symbols`, or inline `candles`; optional `window` = {start, end}
    in ms or `days`. Prefers the local multi-year bn/ cache when available and
    only pages Binance for symbols the cache doesn't cover."""
    if body.get("candles_by_ticker"):
        uni = body["candles_by_ticker"]
        return uni, {"source": "inline", "bars": sum(len(v) for v in uni.values())}
    if body.get("candles"):
        uni = {body.get("symbol", "SERIES"): body["candles"]}
        return uni, {"source": "inline", "bars": len(body["candles"])}

    interval = body.get("interval", "15m")
    limit = int(body.get("limit", 1500))
    start, end = _window(body)

    uni = None
    slug = body.get("universe")
    if slug:
        uni = db.universe_symbols(slug)          # pf_universes is source of truth
        if not uni:
            raise ValueError(f"unknown universe: {slug!r}")
    if uni is None and body.get("symbols"):
        uni = {s: s for s in body["symbols"]}
    if not uni:
        raise ValueError(
            "provide universe, symbols, candles, or candles_by_ticker")
    items = dict(list(uni.items())[:MAX_SYMBOLS])

    cached, seen = _read_cache(items, interval, start, end)
    missing = {tk: sym for tk, sym in items.items() if sym not in seen}
    for tk, sym in missing.items():
        cached[tk] = fetch_candles(sym, interval, limit, start, end)

    if not cached:
        raise ValueError("no candles for this universe/window")
    source = ("cache" if not missing else
              "binance" if not seen else "cache+binance")
    return cached, {"source": source, "bars": sum(len(v) for v in cached.values())}


def _window_meta(uni, meta):
    ts = [k["t"] for rows in uni.values() for k in (rows[0], rows[-1])]
    return {
        "start": _iso_date(min(ts)),
        "end": _iso_date(max(ts)),
        "bars": meta.get("bars", 0),
        "symbols": len(uni),
        "source": meta.get("source", "unknown"),
    }


def _gap_recovery(trades, curve):
    """Honest extras for the report: longest time between signals and the
    longest peak-to-recovery stretch of the equity curve."""
    gap_days = None
    ts = sorted(t["t_sig"] for t in trades if t.get("t_sig") is not None)
    if len(ts) > 1:
        gap_days = round(max(b - a for a, b in zip(ts, ts[1:])) / DAY_MS, 1)

    recovery = None
    if curve:
        peak, peak_t = curve[0][1], curve[0][0]
        dd_depth, dd_peak_t, dd_peak = 0.0, None, None
        for t, eq in curve[1:]:
            if eq >= peak:
                if dd_peak_t is not None and dd_peak is not None and eq >= dd_peak:
                    recovery = round((t - dd_peak_t) / DAY_MS, 1)
                    dd_peak_t = None
                peak, peak_t = eq, t
            else:
                depth = eq / peak - 1 if peak else 0.0
                if depth < dd_depth:
                    dd_depth, dd_peak_t, dd_peak = depth, peak_t, peak
    return {"longest_gap_days": gap_days,
            "drawdown_recovery_days": recovery}


# ---- endpoint functions (HTTP/MCP adapters call these) ----
def ep_health(_body=None):
    return 200, {"ok": True, "service": "paperfleet-engine"}


def ep_catalog(_body=None):
    return 200, build_catalog()


def ep_validate(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 200, {"ok": False, "error": str(e)}
    return 200, {"ok": True, "lookback": s["_lookback"], "side": s["side"],
                 "market": s.get("market"), "fresh": s.get("fresh", False)}


def ep_backtest(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    try:
        uni, meta = _resolve_universe(body)
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    res = (backtest(s, next(iter(uni.values())))
           if len(uni) == 1 else backtest_universe(s, uni))
    return 200, {"ok": True, "stats": res["stats"],
                 "trades": res["trades"][:1000],
                 "window": _window_meta(uni, meta)}


def ep_checks(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    try:
        uni, _meta = _resolve_universe(body)
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, **run_checks(s, uni)}


def ep_evaluate(body):
    """One universe load -> backtest + Trials + Weather.

    The Build worker's single call. Loading the candles once is not just a
    speed-up: the backtest, the stress tests and the condition breakdown all
    see exactly the same tape, so the numbers cannot disagree."""
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    try:
        uni, meta = _resolve_universe(body)
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}

    res = backtest_universe(s, uni)
    checks = run_checks(s, uni, base=res)
    conditions = conditions_breakdown(res["trades"], uni)
    return 200, {
        "ok": True,
        "stats": res["stats"],
        "trades": res["trades"][:1000],
        "window": _window_meta(uni, meta),
        "checks": checks["checks"],
        "checks_passed": checks["passed"],
        "checks_total": checks["total"],
        "conditions": conditions,
        **_gap_recovery(res["trades"], res["stats"].get("equity_curve") or []),
    }


def ep_presets(_body=None):
    """The seed specs, so the frontend doesn't hardcode a copy of presets.py."""
    return 200, {"ok": True,
                 "presets": [_presets.RULE_P, _presets.RULE_P_WICK,
                             _presets.CAPIT]}


def ep_map(body):
    """family_slug + params -> canonical spec (for forking until pf_bots.spec
    is backfilled)."""
    try:
        spec = variant_to_spec(body["family"], body.get("params", {}),
                               body.get("name", ""))
    except (KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, "spec": spec}


ENDPOINTS = {
    ("GET", "/v1/healthz"): ep_health,
    ("GET", "/v1/catalog"): ep_catalog,
    ("GET", "/v1/presets"): ep_presets,
    ("POST", "/v1/validate"): ep_validate,
    ("POST", "/v1/backtest"): ep_backtest,
    ("POST", "/v1/checks"): ep_checks,
    ("POST", "/v1/evaluate"): ep_evaluate,
    ("POST", "/v1/map"): ep_map,
}


# ---- thin HTTP adapter ----
class Handler(BaseHTTPRequestHandler):
    def _run(self, method):
        path = self.path.split("?")[0]
        fn = ENDPOINTS.get((method, path))
        if not fn:
            self._send(404, {"ok": False, "error": "not found"})
            return
        body = {}
        if method == "POST":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                self._send(400, {"ok": False, "error": "bad JSON body"})
                return
        try:
            status, payload = fn(body)
        except Exception as e:                       # never leak a stack trace
            status, payload = 500, {"ok": False, "error": str(e)}
        self._send(status, payload)

    def _send(self, status, payload):
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._run("GET")

    def do_POST(self):
        self._run("POST")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *a):
        pass


def main():
    port = 8099
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print(f"paperfleet engine service: http://localhost:{port}  "
          f"({len(ENDPOINTS)} endpoints)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
