"""The engine service — API-first.

Everything the product needs from the engine is a plain function in ENDPOINTS
(validate / backtest / checks / evaluate / sweep / catalog / health). The
HTTP server below is a thin adapter over them; an MCP server or a direct
Python/API caller would be the same thin adapter over the same functions.

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
from .params import spec_issues
from . import challenges as _challenges
from .sweep import SweepError, expand_prepared, label_for, prepare_axes
from .timeframes import interval_ms as _timeframe_ms
from . import db
from . import presets as _presets
from .export_catalog import build as build_catalog

BINANCE = "https://fapi.binance.com/fapi/v1/klines"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY_MS = 86_400_000

# ---- data ----
MAX_SYMBOLS = 60        # safety cap
MAX_BARS = 200_000      # per-symbol safety cap when paging Binance


def _iso_date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _is_equity_symbol(symbol):
    return not str(symbol).upper().endswith("USDT")


def _fetch_equity(symbol, interval="15m", limit=1500, start=None, end=None):
    """Closed OHLCV bars for an equity ticker via Yahoo Finance chart API."""
    iv_map = {
        "1m": ("1m", "7d"),
        "3m": ("5m", "60d"),
        "5m": ("5m", "60d"),
        "15m": ("15m", "60d"),
        "30m": ("30m", "60d"),
        "1h": ("1h", "730d"),
        "2h": ("1h", "730d"),
        "4h": ("1h", "730d"),
        "6h": ("1h", "730d"),
        "8h": ("1h", "730d"),
        "12h": ("1h", "730d"),
        "1d": ("1d", "5y"),
        "3d": ("1d", "5y"),
        "1w": ("1wk", "5y"),
    }
    yf_iv, yf_rng = iv_map.get(interval, ("15m", "60d"))
    url = f"{YAHOO_CHART}/{symbol}?interval={yf_iv}&range={yf_rng}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read())
        res = (data.get("chart") or {}).get("result") or []
        if not res:
            return []
        block = res[0]
        ts = block.get("timestamp") or []
        quote = ((block.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        vols = quote.get("volume") or []
        out = []
        for i, t_sec in enumerate(ts):
            o = opens[i] if i < len(opens) else None
            h = highs[i] if i < len(highs) else None
            l = lows[i] if i < len(lows) else None
            c = closes[i] if i < len(closes) else None
            v = vols[i] if i < len(vols) else 0
            if o is None or h is None or l is None or c is None:
                continue
            t_ms = int(t_sec) * 1000
            if start and t_ms < int(start):
                continue
            if end and t_ms > int(end):
                continue
            out.append({
                "t": t_ms,
                "o": float(o),
                "h": float(h),
                "l": float(l),
                "c": float(c),
                "v": float(v or 1.0),
            })
        if start is None and limit:
            out = out[-int(limit):]
        return out[:MAX_BARS]
    except Exception:
        return []


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
    """Closed candles from Binance (crypto perps) or Yahoo Finance (equities)."""
    if _is_equity_symbol(symbol):
        return _fetch_equity(symbol, interval, limit, start, end)
    if start is None:
        return _fetch_page(symbol, interval, limit, start, end)

    step = _timeframe_ms(interval)
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


def _with_interval(body, strategy):
    """The strategy's candle size is the source of truth for its data."""
    out = dict(body)
    out["interval"] = strategy.get("_timeframe", "15m")
    return out


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
        rows = fetch_candles(sym, interval, limit, start, end)
        if rows:
            cached[tk] = rows

    cached = {tk: rows for tk, rows in cached.items() if rows}
    if not cached:
        raise ValueError("no candles for this universe/window")
    any_eq = any(_is_equity_symbol(sym) for sym in items.values())
    source = ("yahoo" if any_eq else "cache" if not missing else
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


def _capability_gate(s, target="backtest"):
    """Block a run when the target engine cannot execute the spec. Warnings
    (partial / ignored features) are returned but do not block."""
    issues = spec_issues(s, target)
    blocking = [i for i in issues if i["blocking"]]
    if not blocking:
        return None, issues
    first = blocking[0]
    return {
        "ok": False,
        "error": f"{first['label']} is not supported: {first['reason']}",
        "issues": issues,
    }, issues


def ep_validate(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 200, {"ok": False, "error": str(e)}
    blocked, issues = _capability_gate(s, "backtest")
    if blocked:
        return 200, {**blocked, "lookback": s["_lookback"], "side": s["side"],
                     "market": s.get("market"),
                     "fresh": s.get("fresh", False)}
    return 200, {"ok": True, "lookback": s["_lookback"], "side": s["side"],
                 "market": s.get("market"), "fresh": s.get("fresh", False),
                 "timeframe": s.get("_timeframe"), "issues": issues}


def ep_backtest(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    blocked, issues = _capability_gate(s, "backtest")
    if blocked:
        return 400, blocked
    try:
        uni, meta = _resolve_universe(_with_interval(body, s))
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    res = (backtest(s, next(iter(uni.values())))
           if len(uni) == 1 else backtest_universe(s, uni))
    return 200, {"ok": True, "stats": res["stats"],
                 "trades": res["trades"][:1000],
                 "window": _window_meta(uni, meta),
                 "issues": issues}


def ep_checks(body):
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    blocked, issues = _capability_gate(s, "backtest")
    if blocked:
        return 400, blocked
    try:
        uni, _meta = _resolve_universe(_with_interval(body, s))
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, **run_checks(s, uni), "issues": issues}


def ep_evaluate(body):
    """One universe load -> backtest + Trials + Weather.

    The Build worker's single call. Loading the candles once is not just a
    speed-up: the backtest, the stress tests and the condition breakdown all
    see exactly the same tape, so the numbers cannot disagree."""
    try:
        s = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    blocked, issues = _capability_gate(s, "backtest")
    if blocked:
        return 400, blocked
    try:
        uni, meta = _resolve_universe(_with_interval(body, s))
    except (ValueError, KeyError) as e:
        return 400, {"ok": False, "error": str(e)}

    res = backtest_universe(s, uni)
    checks = run_checks(s, uni, base=res)
    conditions = conditions_breakdown(res["trades"], uni,
                                      bar_ms=s.get("_interval_ms", 900_000))
    return 200, {
        "ok": True,
        "stats": res["stats"],
        "trades": res["trades"][:1000],
        "window": _window_meta(uni, meta),
        "checks": checks["checks"],
        "checks_passed": checks["passed"],
        "checks_total": checks["total"],
        "conditions": conditions,
        "issues": issues,
        **_gap_recovery(res["trades"], res["stats"].get("equity_curve") or []),
    }


def _sweep_stats(stats):
    return {k: stats.get(k) for k in (
        "n", "win_rate", "net_pct_per_trade", "total_net_pct",
        "final_equity", "max_drawdown")}


def ep_sweep(body):
    """Run one backtest per point in a parameter grid.

    Every run reports its own result/error, so an unsupported value or an
    unknown universe fails that row instead of aborting the whole sweep. The
    candle tape is loaded once per universe and reused across variants."""
    try:
        base = parse(body["spec"])
    except (StrategyError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    blocked, base_issues = _capability_gate(base, "backtest")
    if blocked:
        return 400, blocked
    try:
        prepared = prepare_axes(body.get("axes") or [])
    except SweepError as e:
        return 400, {"ok": False, "error": str(e)}

    count = 1
    for _path, values in prepared:
        count *= len(values)

    inline = bool(body.get("candles") or body.get("candles_by_ticker"))
    data_cache = {}
    runs = []
    window = None
    completed = 0
    for variant, changes in expand_prepared(base, prepared):
        row = {"label": label_for(changes), "changes": changes,
               "stats": None, "error": None}
        try:
            s = parse(variant)
        except (StrategyError, KeyError, TypeError) as e:
            row["error"] = str(e)
            runs.append(row)
            continue
        blocked, issues = _capability_gate(s, "backtest")
        if blocked:
            row["error"] = blocked["error"]
            row["issues"] = blocked["issues"]
            runs.append(row)
            continue

        try:
            iv = s.get("_timeframe", base.get("_timeframe", "15m"))
            if inline and iv != base.get("_timeframe", "15m"):
                raise ValueError(
                    "inline candles are fixed to the base candle size; "
                    "use a market universe/symbols for a timeframe sweep")
            data_body = _with_interval(body, s)
            if inline:
                key = ("inline",)
                if key not in data_cache:
                    data_cache[key] = _resolve_universe(data_body)
            elif body.get("symbols"):
                key = ("symbols", iv)
                if key not in data_cache:
                    data_cache[key] = _resolve_universe(data_body)
            else:
                slug = s.get("universe") or body.get("universe")
                if not slug:
                    raise ValueError(
                        "provide universe, symbols, candles, or candles_by_ticker")
                key = (iv, slug)
                if key not in data_cache:
                    data_cache[key] = _resolve_universe(
                        {**data_body, "universe": slug, "symbols": None})
            uni, meta = data_cache[key]
            res = backtest_universe(s, uni)
        except (ValueError, KeyError, TypeError) as e:
            row["error"] = f"data: {e}"
            runs.append(row)
            continue

        row["stats"] = _sweep_stats(res["stats"])
        if issues:
            row["issues"] = issues
        if window is None:
            window = _window_meta(uni, meta)
        completed += 1
        runs.append(row)

    return 200, {"ok": True, "count": count, "completed": completed,
                 "window": window, "runs": runs, "issues": base_issues}


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


def ep_enter_challenge(body):
    """Validate a Copy of a challenge template as a legal entry.

    The lock-set is the engine's, not the UI's: the entry may differ from the
    template only at the open holes, every predicate must hold, and the result
    must still be a runnable strategy. Give either a full `candidate` spec or a
    map of `edits` (hole path -> value) applied to the template.

        body = {template, lock_set:{holes, predicates}, candidate?|edits?}
    """
    template = body.get("template")
    lock_set = body.get("lock_set") or {}
    holes = lock_set.get("holes") or []
    predicates = lock_set.get("predicates") or []
    if not isinstance(template, dict):
        return 400, {"ok": False, "error": "a template spec is required"}

    try:
        if body.get("candidate") is not None:
            candidate = body["candidate"]
        else:
            candidate = _challenges.build_entry(template, body.get("edits") or {}, holes)
    except (ValueError, KeyError, TypeError) as e:
        return 200, {"ok": False, "error": str(e)}

    # the Weather gate lives on the bot row, not the strategy tree; carry it
    # onto the candidate so predicates like no_weather can see it.
    if "condition_filter" in body:
        candidate = {**candidate, "condition_filter": body["condition_filter"]}

    ok, err = _challenges.validate_entry(template, candidate, holes, predicates)
    if not ok:
        return 200, {"ok": False, "error": err}

    # a legal entry must still be a runnable strategy the target can execute
    try:
        s = parse(candidate)
    except (StrategyError, KeyError, TypeError) as e:
        return 200, {"ok": False, "error": str(e)}
    blocked, issues = _capability_gate(s, "backtest")
    if blocked:
        return 200, {**blocked, "ok": False}
    return 200, {"ok": True, "spec": candidate, "lookback": s["_lookback"],
                 "side": s["side"], "issues": issues}


def ep_score_challenge(body):
    """Rank a challenge's entries by its judge.

        body = {entries:[{id, result}], judge, judge_cfg?}
    `result` is a backtest/live result ({stats, trades}). Returns standings,
    winner first; ineligible entries (e.g. below a trade floor) place last.

    INTEGRITY: results MUST be produced by the engine over the real market
    window (the worker calls this with its own run output). Never pass results
    supplied by a client — a Builder could forge their own P&L."""
    try:
        standings = _challenges.rank(body.get("entries") or [],
                                     body.get("judge", "return"),
                                     body.get("judge_cfg") or {})
    except (ValueError, KeyError, TypeError) as e:
        return 400, {"ok": False, "error": str(e)}
    return 200, {"ok": True, "standings": standings}


ENDPOINTS = {
    ("GET", "/v1/healthz"): ep_health,
    ("GET", "/v1/catalog"): ep_catalog,
    ("GET", "/v1/presets"): ep_presets,
    ("POST", "/v1/validate"): ep_validate,
    ("POST", "/v1/backtest"): ep_backtest,
    ("POST", "/v1/checks"): ep_checks,
    ("POST", "/v1/evaluate"): ep_evaluate,
    ("POST", "/v1/sweep"): ep_sweep,
    ("POST", "/v1/map"): ep_map,
    ("POST", "/v1/challenge/enter"): ep_enter_challenge,
    ("POST", "/v1/challenge/score"): ep_score_challenge,
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
