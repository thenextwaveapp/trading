#!/usr/bin/env python3
"""HTTP backend for the fleet web app. Stdlib only.

Serves the built React app from web_dist and a small JSON API it reads:
/api (fleet payload: health, P&L, positions marked to live prices, equity
curves, trades, log tail), /candles (chart data), /healthz. A watchdog thread
alerts via ntfy if the fleet process dies. This is the server behind
fleet.presencenet.io.

Usage: python3 -m runtime.server.app        # http://127.0.0.1:8787
       python3 -m runtime.server.app --port 9000
       python3 -m runtime.server.app --lan  # bind 0.0.0.0
"""
import csv
import fcntl
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import base64
import hmac
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..fleet.runner import (DIR, LOG, START_EQUITY, M15, PAUSE, NTFY_CFG,
                         notify, ntfy_topic, load_state, tpath, pstr, btc_bear)
from ..trade_model import klines

BIN = "https://fapi.binance.com/fapi/v1/klines"

# ---- DB fleet (pf_bots) ----
# Read the DB fleet + the pickable coin set for /candles validation. Cached so
# a 10s /api poll doesn't hammer the DB. Service env supplies SUPABASE_*.
import urllib.parse as _uparse
_SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SB_KEY = (os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_ANON_KEY", ""))
_fcache = {}


def _sb_get(path, params, ttl=60):
    key = (path, tuple(sorted(params.items())))
    hit = _fcache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{path}?{_uparse.urlencode(params)}",
        headers={"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        val = json.loads(r.read())
    _fcache[key] = (time.time(), val)
    return val


def fleet_bots():
    """The live DB fleet: public/visible bots that are deployed."""
    return _sb_get("pf_bots", {
        "select": "id,name,bt,direction,visibility",
        "stage": "eq.deployed",
        "visibility": "neq.private", "order": "name"})


def coin_map():
    """ticker -> binance_symbol over the real instrument table (pf_instruments), for the
    chart modal and /candles validation. Falls back to the local 60 map."""
    try:
        rows = _sb_get("pf_instruments", {"select": "symbol,binance_symbol"}, ttl=3600)
        m = {r["symbol"]: r["binance_symbol"] for r in rows
             if r.get("binance_symbol")}
        return m
    except Exception:
        return {}


def valid_symbols():
    return set(coin_map().values())
IVALS = {"1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"}
# Built React app (web/dist copied here on deploy). Served at / with an SPA
# fallback to index.html; if the build is absent, / returns 503.
WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web_dist")


# ---- dashboard auth ----
# Viewing is public — the dashboard shows the same fleet data as the public
# site. Only the controls (POST: start/stop/restart/pause) are gated: a
# Cloudflare tunnel fronts the public site via localhost, so every request
# arrives as 127.0.0.1 and IP-based trust is meaningless, so the POST handler
# requires HTTP Basic credentials. Source, first hit wins: env FLEET_DASH_USER +
# FLEET_DASH_PASS, then the gitignored paper/fleet/dash_auth.json
# ({"user": .., "pass": ..}).
def _load_auth():
    u, p = os.environ.get("FLEET_DASH_USER"), os.environ.get("FLEET_DASH_PASS")
    if u and p:
        return (u, p)
    try:
        with open(os.path.join(DIR, "dash_auth.json")) as f:
            c = json.load(f)
        if c.get("user") and c.get("pass"):
            return (c["user"], c["pass"])
    except (OSError, ValueError):
        pass
    return None


AUTH = _load_auth()


def fetch_candles(sym, interval, limit, start=None, end=None):
    """Closed candles at any whitelisted interval, pageable backwards via
    end — lets the chart lazy-load history to the perp's listing date.
    Crypto perps come from Binance; equities/FX (non-USDT symbols) route to the
    engine's Yahoo fetch so their charts work in prod, not just dev."""
    if not str(sym).upper().endswith("USDT"):
        try:
            from core.service import fetch_candles as _engine_candles
            return _engine_candles(sym, interval, limit, start, end)
        except Exception:
            return []
    url = f"{BIN}?symbol={sym}&interval={interval}&limit={limit}"
    if start:
        url += f"&startTime={start}"
    if end:
        url += f"&endTime={end}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        return [dict(t=int(x[0]), o=float(x[1]), h=float(x[2]),
                     l=float(x[3]), c=float(x[4]))
                for x in rows if int(x[6]) <= now]
    except Exception:
        return []
LWJS = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets",
                         "lightweight-charts.standalone.production.js"),
            "rb").read()

# Dashboard display config.
BENCH = 2.0                    # reference return line, %
STALE_S = 25 * 60             # marks older than this flag the fleet stale

# trade-direction labels for the payload's per-direction grouping
_DLBL = {"short": "Short — pump fades",
         "long": "Long — capitulation + momentum",
         "both": "Both — two-sided books"}

LINUX = sys.platform.startswith("linux")
FLEET_SVC = f"gui/{os.getuid()}/com.trading.paperfleet"
FLEET_PLIST = os.path.expanduser(
    "~/Library/LaunchAgents/com.trading.paperfleet.plist")
FLEET_UNIT = "trading-paperfleet"
PX_API = "https://fapi.binance.com/fapi/v1/ticker/price"


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as e:
        return False, repr(e)


def fleet_running():
    """The fleet holds an exclusive flock on fleet.lock while its loop runs; if
    we can grab the lock, it is not running."""
    path = os.path.join(DIR, "fleet.lock")
    if not os.path.exists(path):
        return None
    try:
        f = open(path)
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
        return False
    except OSError:
        return True


def fleet_loaded():
    if LINUX:
        return subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", FLEET_UNIT],
            capture_output=True).returncode == 0
    return subprocess.run(["/bin/launchctl", "print", FLEET_SVC],
                          capture_output=True).returncode == 0


_px_cache = {}


def live_px(symbol):
    c = _px_cache.get(symbol)
    if c and time.time() - c[0] < 10:
        return c[1]
    try:
        with urllib.request.urlopen(f"{PX_API}?symbol={symbol}",
                                    timeout=5) as r:
            px = float(json.loads(r.read())["price"])
        _px_cache[symbol] = (time.time(), px)
        return px
    except Exception:
        return None


def fleet_start_ms():
    try:
        with open(LOG) as f:
            first = f.readline()[:19]
        dt = datetime.strptime(first, "%Y-%m-%d %H:%M:%S")
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000) - 7 * 86_400_000


def recent_errors():
    if not os.path.exists(LOG):
        return 0, None
    cut = (datetime.now(timezone.utc).timestamp() - 86400)
    n, last = 0, None
    with open(LOG) as f:
        for ln in f.readlines()[-500:]:
            if "ERROR" not in ln[20:32]:
                continue
            try:
                ts = datetime.strptime(ln[:19], "%Y-%m-%d %H:%M:%S") \
                    .replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
            if ts >= cut:
                n, last = n + 1, ln.strip()
    return n, last


def health(running, state_age, paused):
    nerr, last_err = recent_errors()
    if running is False:
        return dict(status="red", msg="NOT SCANNING — fleet process is down."
                    " Hit start, or check paper/fleet/launchd.err.log",
                    errors24=nerr, last_error=last_err)
    if state_age is None or state_age > STALE_S:
        age = "never" if state_age is None else f"{state_age//60}m ago"
        return dict(status="red" if running is None else "amber",
                    msg=f"process alive but last completed cycle was {age} — "
                        "data feed or network trouble, check the log",
                    errors24=nerr, last_error=last_err)
    if paused:
        return dict(status="amber", msg="TRADING PAUSED — no new entries; "
                    "open positions still managed. Resume below.",
                    errors24=nerr, last_error=last_err)
    if nerr:
        return dict(status="amber",
                    msg=f"scanning (last cycle {state_age//60}m ago), but "
                        f"{nerr} cycle error(s) in the last 24h — see log",
                    errors24=nerr, last_error=last_err)
    return dict(status="green",
                msg=f"scanning — last cycle {state_age//60}m ago, "
                    "all bots live",
                errors24=0, last_error=None)


def payload():
    now = int(time.time() * 1000)
    g = dict(bear=btc_bear())
    start = fleet_start_ms()
    out, all_trades, open_all, dirs = [], [], [], {}
    try:
        bots = fleet_bots()
    except Exception:
        bots = []
    for b in bots:
        name, bid, d = b["name"], b["id"], (b.get("direction") or "both")
        st = load_state(bid)                     # per-bot-id state (new format)
        trades = sorted(st.get("trades", []), key=lambda t: t["exit_t"])
        nets = [t["net"] for t in trades]
        opens = []
        for p in st.get("positions", []):
            side = p.get("side", -1)
            px = live_px(p["symbol"])
            upct = side * (px / p["entry"] - 1) if px else None
            opens.append(dict(
                bot=name, ticker=p["ticker"],
                side="long" if side == 1 else "short",
                entry=p["entry"], px=px,
                upct=upct, upnl=p["notional"] * upct if upct is not None
                else None,
                stop=p["stop"],
                room=((p["stop"] - px) / px if side == -1 else
                      (px - p["stop"]) / px) if px else None,
                notional=round(p["notional"], 2), t_sig=p["t_sig"],
                tp=p.get("tp"),
                exits_at=p["t_sig"] + p["hold"] * M15))
        open_all += opens
        # curve: realized equity steps (eq_hist) ending at the live mark
        unreal = sum(o["upnl"] for o in opens if o["upnl"] is not None)
        curve = sorted(
            [[start, START_EQUITY]] +
            [[int(t), eq] for t, eq in st.get("eq_hist", [])] +
            [[now, round(st["equity"] + unreal, 2)]])
        out.append(dict(
            name=name, params=d,
            equity=round(st["equity"], 2),
            ret=round((st["equity"] / START_EQUITY - 1) * 100, 3),
            open=opens, closed=len(trades),
            win=round(sum(1 for n in nets if n > 0) / len(nets) * 100)
                if nets else None,
            avg=round(sum(nets) / len(nets) * 100, 3) if nets else None,
            bt=b.get("bt"), curve=curve,
            kill=st.get("kill_until", 0) > now,
            group=d, note=None, cfg=None))
        for t in trades:
            all_trades.append(dict(t, bot=name))
        dirs.setdefault(d, dict(label=_DLBL.get(d, d), bots=[]))[
            "bots"].append(name)
    all_trades.sort(key=lambda t: t["exit_t"], reverse=True)
    strats = {k: dirs[k] for k in ("short", "long", "both") if k in dirs}
    top = max(out, key=lambda v: v["equity"], default=None)
    hero = dict(
        base_pnl=round(top["equity"] - START_EQUITY, 2) if top else 0,
        base_ret=top["ret"] if top else 0,
        base_closed=top["closed"] if top else 0,
        base_avg=top["avg"] if top else None, bench=BENCH,
        fleet_pnl=round(sum(v["equity"] for v in out)
                        - len(out) * START_EQUITY, 2),
        unreal=round(sum(p["upnl"] for p in open_all
                         if p["upnl"] is not None), 2),
        week_pnl=round(sum(t["pnl"] for t in all_trades
                           if t["exit_t"] >= now - 7 * 86_400_000), 2),
        closed=len(all_trades))
    tail = []
    if os.path.exists(LOG):
        with open(LOG) as f:
            tail = [ln.rstrip() for ln in f.readlines()[-30:]]
    state_mtime = max((os.path.getmtime(p) for p in
                       (os.path.join(DIR, f"{b['id']}.json") for b in bots)
                       if os.path.exists(p)), default=0)
    age = round(time.time() - state_mtime) if state_mtime else None
    running = fleet_running()
    paused = os.path.exists(PAUSE)
    return dict(now=now, start=start, gate=g, hero=hero, bots=out,
                strats=strats,
                positions=open_all, trades=all_trades[:100],
                log=tail, running=running, loaded=fleet_loaded(),
                paused=paused,
                health=health(running, age, paused),
                ntfy=ntfy_topic() or "", state_age_s=age, cmds=[],
                symbols=coin_map())


def redact_for_public(d):
    """Strip operator-only telemetry + secrets from an /api payload for viewers
    without dashboard credentials. The fleet's *performance* (equity, positions,
    trades, curves) stays public — that is the verified track record the product
    is built on — but the log tail, the ntfy alert topic (a shared secret:
    anyone who has it can read the fleet's phone alerts), the queued-ops list,
    and the health detail (which names internal paths) are not."""
    d["log"] = []
    d["ntfy"] = ""
    d["cmds"] = []
    h = d.get("health") or {}
    d["health"] = {"status": h.get("status", "green"), "msg": "",
                   "errors24": 0, "last_error": None}


# ---- controls ----

def watchdog():
    """Push a phone alert when the fleet process disappears / comes back."""
    prev = fleet_running()
    while True:
        time.sleep(60)
        cur = fleet_running()
        if cur is False and prev:
            notify("FLEET DOWN", "the paper fleet process is not running — "
                   "open the dashboard to restart it",
                   priority="urgent", tags="rotating_light")
        if cur and prev is False:
            notify("Fleet back up", "scanning resumed",
                   tags="white_check_mark")
        prev = cur


def ensure_ntfy():
    if not os.path.exists(NTFY_CFG):
        json.dump(dict(topic=f"pumpfleet-{secrets.token_hex(5)}",
                       enabled=True), open(NTFY_CFG, "w"))




class Handler(BaseHTTPRequestHandler):
    def _authed(self):
        """True if auth is unconfigured or valid Basic credentials given."""
        if not AUTH:
            return True
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(hdr[6:]).decode(
                "utf-8", "replace").partition(":")
        except Exception:
            return False
        # constant-time compare both halves to avoid leaking via timing
        return (hmac.compare_digest(user, AUTH[0])
                & hmac.compare_digest(pw, AUTH[1]))

    def _deny(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate",
                         'Basic realm="fleet", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":          # unauthenticated liveness probe, no data
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if path == "/api":
            d = payload()
            d["local"] = self.client_address[0] in ("127.0.0.1", "::1")
            # Viewing the fleet is public, but its operational telemetry and
            # secrets are not — redact them unless the request carries valid
            # dashboard credentials (the same gate the controls use).
            if not self._authed():
                redact_for_public(d)
            body = json.dumps(d).encode()
            ctype = "application/json"
        elif path == "/lw.js":
            body, ctype = LWJS, "application/javascript"
        elif path == "/candles":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            sym = q.get("symbol", [""])[0]
            iv = q.get("interval", ["15m"])[0]
            if sym not in valid_symbols() or iv not in IVALS:
                self.send_error(404)
                return
            try:
                start = int(q.get("start", ["0"])[0]) or None
                end = int(q.get("end", ["0"])[0]) or None
                limit = max(10, min(int(q.get("limit", ["400"])[0]), 10_000))
            except ValueError:
                self.send_error(400)
                return
            body = json.dumps(fetch_candles(sym, iv, limit, start,
                                            end)).encode()
            ctype = "application/json"
        else:
            self._serve_spa(path)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_spa(self, path):
        # Serve the built React app from WEB_DIST. Real files are served
        # directly; anything else falls back to index.html so client-side
        # routes (/research, /leaderboard, ...) resolve. If the build isn't
        # deployed, there's nothing to serve.
        if not os.path.isdir(WEB_DIST):
            self.send_error(503, "web build not deployed")
            return
        target = os.path.normpath(os.path.join(WEB_DIST, path.lstrip("/")))
        if not target.startswith(WEB_DIST + os.sep) or not os.path.isfile(target):
            target = os.path.join(WEB_DIST, "index.html")   # SPA fallback
        try:
            with open(target, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        # hashed asset filenames are immutable; the HTML shell must not cache
        cache = "no-store" if target.endswith("index.html") \
            else "public, max-age=31536000, immutable"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):           # keep stdout quiet
        pass


def main():
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    port = 8787
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    ensure_ntfy()
    threading.Thread(target=watchdog, daemon=True).start()
    if AUTH is None:
        print("WARNING: dashboard auth NOT configured — fleet controls are OPEN "
              "and operational data (log tail, alert topic) is served to every "
              "viewer. Set FLEET_DASH_USER/FLEET_DASH_PASS or "
              "paper/fleet/dash_auth.json.")
    else:
        print(f"control auth: enabled (user {AUTH[0]!r})")
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"fleet dashboard: http://{'localhost' if host != '0.0.0.0' else host}:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
