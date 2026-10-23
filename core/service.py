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
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .strategy import parse, StrategyError
from .backtest import backtest, backtest_universe
from .checks import run_checks
from .mapping import variant_to_spec
from . import db
from . import presets as _presets
from .export_catalog import build as build_catalog

BINANCE = "https://fapi.binance.com/fapi/v1/klines"


# ---- data ----
MAX_SYMBOLS = 60        # safety cap


def fetch_candles(symbol, interval="15m", limit=1500, start=None, end=None):
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


def _resolve_universe(body):
    """-> {ticker: candles}. Resolves universe->symbols and fetches candles:
    callers send a `universe` slug (fleet-60 / majors), or `symbols`, or inline
    `candles`/`candles_by_ticker`. Optional `window` = {start, end} in ms.
    Candles are fetched live from Binance (no cache yet), so big universes over
    long windows are slow."""
    if body.get("candles_by_ticker"):
        return body["candles_by_ticker"]
    if body.get("candles"):
        return {body.get("symbol", "SERIES"): body["candles"]}
    interval = body.get("interval", "15m")
    limit = int(body.get("limit", 1500))
    win = body.get("window") or {}
    start, end = win.get("start"), win.get("end")

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
    items = list(uni.items())[:MAX_SYMBOLS]
    return {tk: fetch_candles(sym, interval, limit, start, end)
            for tk, sym in items}


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
        uni = _resolve_universe(body)
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    res = (backtest(s, next(iter(uni.values())))
           if len(uni) == 1 else backtest_universe(s, uni))
    return 200, {"ok": True, "stats": res["stats"],
                 "trades": res["trades"][:1000]}


def ep_checks(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    try:
        uni = _resolve_universe(body)
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, **run_checks(s, uni)}


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
