"""The engine service — API-first. The missing organ.

Everything the product needs from the engine is a plain function in ENDPOINTS
(validate / backtest / checks / catalog / health). The HTTP server below is a
thin adapter over them; an MCP server or a direct Python/API caller is the
same thin adapter over the SAME functions. That's how this is API- and
MCP-friendly by construction, not by retrofit.

Data: endpoints accept candles inline — `candles` (one series) or
`candles_by_ticker` ({ticker: [...]}) — for pure, offline, deterministic
compute. If given `symbols` + `interval`/`limit` instead, the service fetches
closed candles from Binance so it can run on real market data.

Run:  python3 -m core.service [--port 8099]
Test: curl -s localhost:8099/v1/healthz
"""
import json
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .strategy import parse, StrategyError
from .backtest import backtest, backtest_universe
from .checks import run_checks
from .export_catalog import build as build_catalog

BINANCE = "https://fapi.binance.com/fapi/v1/klines"


# ---- data ----------------------------------------------------------------
def fetch_candles(symbol, interval="15m", limit=1000):
    url = f"{BINANCE}?symbol={symbol}&interval={interval}&limit={limit}"
    with urllib.request.urlopen(url, timeout=20) as r:
        rows = json.loads(r.read())
    import time
    now = int(time.time() * 1000)
    return [dict(t=int(x[0]), o=float(x[1]), h=float(x[2]), l=float(x[3]),
                 c=float(x[4]), v=float(x[5]))
            for x in rows if int(x[6]) <= now]


def _resolve_universe(body):
    """Return {ticker: candles} from inline candles or a Binance fetch."""
    if body.get("candles_by_ticker"):
        return body["candles_by_ticker"]
    if body.get("candles"):
        return {body.get("symbol", "SERIES"): body["candles"]}
    symbols = body.get("symbols")
    if symbols:
        interval = body.get("interval", "15m")
        limit = int(body.get("limit", 1000))
        return {s: fetch_candles(s, interval, limit) for s in symbols}
    raise ValueError("provide candles, candles_by_ticker, or symbols")


# ---- endpoint functions (the real API — HTTP/MCP just call these) --------
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


ENDPOINTS = {
    ("GET", "/v1/healthz"): ep_health,
    ("GET", "/v1/catalog"): ep_catalog,
    ("POST", "/v1/validate"): ep_validate,
    ("POST", "/v1/backtest"): ep_backtest,
    ("POST", "/v1/checks"): ep_checks,
}


# ---- thin HTTP adapter ---------------------------------------------------
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
