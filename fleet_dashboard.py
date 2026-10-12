#!/usr/bin/env python3
"""Local web dashboard + remote control for the paper fleet. Stdlib only.

Serves a self-contained HTML page (no internet needed to render) showing:
health banner, P&L headline, open positions marked to live prices, equity
curves, per-variant table, trades, pump events, log tail. Control buttons
(loopback-only): start/stop/restart the fleet (launchd), pause/resume
trading (PAUSED flag file), keep-awake toggle (pmset), ntfy phone alerts
(topic config + test). A watchdog thread pushes a phone alert if the fleet
process dies.

Usage: python3 fleet_dashboard.py              # http://127.0.0.1:8787
       python3 fleet_dashboard.py --port 9000
       python3 fleet_dashboard.py --lan        # bind 0.0.0.0 (view from phone;
                                               # controls stay loopback-only)
"""
import csv
import fcntl
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from paper_fleet import (VARIANTS, BT, STRATS, OPS, DIR, LOG, START_EQUITY,
                         M15, PAUSE, NTFY_CFG, notify, ntfy_topic, load_state,
                         load_events, gate_state, tpath, pstr, btc_bear,
                         load_cmds, save_cmds, CFG)
from paper_trader import klines

UNI = json.load(open(os.path.join(os.path.dirname(DIR), "universe60.json")))
BIN = "https://fapi.binance.com/fapi/v1/klines"
IVALS = {"15m", "1h", "4h", "1d"}


def fetch_candles(sym, interval, limit, start=None, end=None):
    """Closed candles at any whitelisted interval, pageable backwards via
    end — lets the chart lazy-load history to the perp's listing date."""
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
LWJS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets",
                         "lightweight-charts.standalone.production.js"),
            "rb").read()

# BT (backtest reference), strategy grouping, benchmark, staleness and port
# all come from fleet_config.json via paper_fleet — single source of truth.
BENCH = OPS.get("benchmark_pct", 2.0)
STALE_S = OPS.get("stale_minutes", 25) * 60

# per-variant metadata for the detail modal: group label, note, raw config
VMETA = {}
for _sk, _s in CFG["strategies"].items():
    for _vn, _v in _s["variants"].items():
        VMETA[_vn] = dict(group=_s.get("label", _sk), note=_v.get("note"),
                          cfg={k: v for k, v in _v.items() if k != "note"})


def _direction(cfg):
    if cfg.get("twosided") or cfg.get("engine") in ("super", "churn"):
        return "both"
    if cfg.get("engine") in ("momo", "capit", "loser"):
        return "long"
    return "short"


# tab grouping by trade direction (all / short / long / both)
_DLBL = {"short": "Short — pump fades",
         "long": "Long — capitulation + momentum",
         "both": "Both — two-sided books"}
DIRS = {}
for _n, _c in VARIANTS.items():
    _d = _direction(_c)
    DIRS.setdefault(_d, dict(label=_DLBL[_d], variants=[]))["variants"].append(_n)
DIRS = {k: DIRS[k] for k in ("short", "long", "both") if k in DIRS}

FLEET_SVC = f"gui/{os.getuid()}/com.trading.paperfleet"
FLEET_PLIST = os.path.expanduser(
    "~/Library/LaunchAgents/com.trading.paperfleet.plist")
PX_API = "https://fapi.binance.com/fapi/v1/ticker/price"


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as e:
        return False, repr(e)


def fleet_running():
    """The fleet holds an exclusive flock on fleet.lock while its loop runs;
    if we can grab the lock, nobody is home."""
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
    return subprocess.run(["/bin/launchctl", "print", FLEET_SVC],
                          capture_output=True).returncode == 0


def sleep_disabled():
    ok, out = run_cmd(["/usr/bin/pmset", "-g"])
    for ln in out.splitlines():
        if "SleepDisabled" in ln:
            return ln.split()[-1] == "1"
    return False


_px_cache = {}


def live_px(symbol):
    c = _px_cache.get(symbol)
    if c and time.time() - c[0] < 30:
        return c[1]
    try:
        with urllib.request.urlopen(f"{PX_API}?symbol={symbol}",
                                    timeout=5) as r:
            px = float(json.loads(r.read())["price"])
        _px_cache[symbol] = (time.time(), px)
        return px
    except Exception:
        return None


def read_trades(name):
    if not os.path.exists(tpath(name)):
        return []
    rows = [r for r in list(csv.reader(open(tpath(name))))[1:]
            if r and r[0] != "ticker"]
    out = []
    for r in rows:
        try:
            out.append(dict(ticker=r[0], t_sig=int(float(r[1])), entry=float(r[2]),
                            stop=float(r[3]), exit_t=int(float(r[4])), kind=r[5],
                            net=float(r[6]), pnl=float(r[7]), notional=float(r[8]),
                            equity_after=float(r[9])))
        except (ValueError, IndexError):
            continue
    return out


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
                    "all 12 variants live",
                errors24=0, last_error=None)


def payload():
    now = int(time.time() * 1000)
    store = load_events()
    g = gate_state(store)
    g["bear"] = btc_bear()
    start = fleet_start_ms()
    variants, all_trades, open_all = [], [], []
    for name, cfg in VARIANTS.items():
        st = load_state(name)
        trades = sorted(read_trades(name), key=lambda t: t["exit_t"])
        nets = [t["net"] for t in trades]
        opens = []
        for p in st["positions"]:
            side = p.get("side", -1)
            px = live_px(p["symbol"])
            upct = side * (px / p["entry"] - 1) if px else None
            opens.append(dict(
                variant=name, ticker=p["ticker"],
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
        # curve ends marked-to-market: realized equity + open unrealized
        unreal = sum(p["upnl"] for p in opens if p["upnl"] is not None)
        curve = [[start, START_EQUITY]] + \
                [[t["exit_t"], t["equity_after"]] for t in trades] + \
                [[now, round(st["equity"] + unreal, 2)]]
        variants.append(dict(
            name=name, params=pstr(cfg),
            equity=round(st["equity"], 2),
            ret=round((st["equity"] / START_EQUITY - 1) * 100, 3),
            open=opens, closed=len(trades),
            win=round(sum(1 for n in nets if n > 0) / len(nets) * 100)
                if nets else None,
            avg=round(sum(nets) / len(nets) * 100, 3) if nets else None,
            bt=BT.get(name), curve=curve,
            kill=st["kill_until"] > now,
            group=VMETA.get(name, {}).get("group"),
            note=VMETA.get(name, {}).get("note"),
            cfg=VMETA.get(name, {}).get("cfg")))
        for t in trades:
            all_trades.append(dict(t, variant=name))
    all_trades.sort(key=lambda t: t["exit_t"], reverse=True)
    base = next(v for v in variants if v["name"] == "base")
    hero = dict(
        base_pnl=round(base["equity"] - START_EQUITY, 2),
        base_ret=base["ret"], base_closed=base["closed"],
        base_avg=base["avg"], bench=BENCH,
        fleet_pnl=round(sum(v["equity"] for v in variants)
                        - len(variants) * START_EQUITY, 2),
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
                       (os.path.join(DIR, f"{n}.json") for n in VARIANTS)
                       if os.path.exists(p)), default=0)
    age = round(time.time() - state_mtime) if state_mtime else None
    running = fleet_running()
    paused = os.path.exists(PAUSE)
    events = sorted(store["events"], key=lambda e: e["t"], reverse=True)[:40]
    return dict(now=now, start=start, gate=g, hero=hero, variants=variants,
                strats=DIRS,
                positions=open_all, trades=all_trades[:100], events=events,
                log=tail, running=running, loaded=fleet_loaded(),
                awake=sleep_disabled(), paused=paused,
                health=health(running, age, paused),
                ntfy=ntfy_topic() or "", state_age_s=age, cmds=load_cmds(),
                symbols=UNI)


# ---------------------------------------------------------------- controls

AWAKE_HELP = ("keep-awake needs a one-time setup — run in a terminal:  "
              "sudo bash launchd/allow_pmset.sh")


def set_pause(on):
    if on:
        with open(PAUSE, "w") as f:
            f.write("paused via dashboard\n")
    else:
        try:
            os.remove(PAUSE)
        except FileNotFoundError:
            pass
    return True, ("paused — takes effect next cycle (<15 min); "
                  "open positions still managed") if on else "resumed"


def set_ntfy(topic):
    json.dump(dict(topic=topic, enabled=bool(topic)), open(NTFY_CFG, "w"))
    return True, f"alerts topic set to '{topic}'" if topic else "alerts off"


def ntfy_test():
    topic = ntfy_topic()
    if not topic:
        return False, "no topic set"
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data="test from the fleet dashboard — alerts are working".encode(),
            headers={"Title": "Paper Fleet", "Tags": "white_check_mark"})
        urllib.request.urlopen(req, timeout=10)
        return True, f"sent — check the ntfy app (topic: {topic})"
    except Exception as e:
        return False, repr(e)


ACTIONS = {
    "fleet_stop": lambda b: run_cmd(
        ["/bin/launchctl", "bootout", FLEET_SVC]),
    "fleet_start": lambda b: run_cmd(
        ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", FLEET_PLIST]),
    "fleet_restart": lambda b: run_cmd(
        ["/bin/launchctl", "kickstart", "-k", FLEET_SVC]),
    "awake_on": lambda b: run_cmd(
        ["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", "1"]),
    "awake_off": lambda b: run_cmd(
        ["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", "0"]),
    "pause_on": lambda b: set_pause(True),
    "pause_off": lambda b: set_pause(False),
    "set_ntfy": lambda b: set_ntfy(str(b.get("topic", "")).strip()),
    "ntfy_test": lambda b: ntfy_test(),
    "close": lambda b: queue_close(b),
    "tp": lambda b: queue_tp(b),
}


def _pos_ref(b):
    if b.get("v") not in VARIANTS:
        return None, (False, "unknown variant")
    try:
        return dict(v=b["v"], tk=str(b.get("tk", "")),
                    t_sig=int(b.get("t_sig"))), None
    except (TypeError, ValueError):
        return None, (False, "bad t_sig")


def queue_close(b):
    """Queue a manual close (one position) for the fleet's next cycle."""
    ref, err = _pos_ref(b)
    if err:
        return err
    cmd = dict(scope="trade", **ref)
    cmds = load_cmds()
    if cmd in cmds:
        return True, "already queued"
    cmds.append(cmd)
    save_cmds(cmds)
    return True, "queued — fills on the fleet's next cycle (<= 15 min)"


def queue_tp(b):
    """Queue a take-profit set/clear on one position. tp=null clears
    (back to the default time exit)."""
    ref, err = _pos_ref(b)
    if err:
        return err
    tp = b.get("tp")
    if tp is not None:
        try:
            tp = float(tp)
        except (TypeError, ValueError):
            return False, "bad tp price"
        if not tp > 0:
            return False, "bad tp price"
    cmd = dict(type="tp", tp=tp, **ref)
    # replace any earlier tp command for the same position
    cmds = [c for c in load_cmds()
            if not (c.get("type") == "tp" and c.get("v") == ref["v"]
                    and c.get("tk") == ref["tk"]
                    and c.get("t_sig") == ref["t_sig"])]
    cmds.append(cmd)
    save_cmds(cmds)
    return True, ("TP queued — active from the fleet's next cycle"
                  if tp else "TP clear queued")


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


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paper Fleet</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
--green:#3fb950;--red:#f85149;--amber:#d29922;--blue:#58a6ff}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;padding:16px;max-width:1200px;margin:0 auto}
h1{font-size:18px;margin-bottom:10px}
h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:24px 0 8px}
#banner{border-radius:8px;padding:10px 16px;font-size:15px;font-weight:600;margin-bottom:12px;border:1px solid}
#banner.green{background:rgba(63,185,80,.1);border-color:#238636;color:var(--green)}
#banner.amber{background:rgba(210,153,34,.1);border-color:#9e6a03;color:var(--amber)}
#banner.red{background:rgba(248,81,73,.12);border-color:#da3633;color:var(--red)}
.hero{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 16px;min-width:130px;flex:1}
.stat .v{font-size:22px;font-weight:650}
.stat .l{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.stat .s{font-size:11px;color:var(--dim)}
.pills{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}
.pill{border:1px solid var(--line);border-radius:999px;padding:2px 12px;font-size:12px;background:var(--card)}
.pill b{font-weight:600}
.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}.dim{color:var(--dim)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:13px}
th,td{padding:5px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.scroll{overflow-x:auto;border-radius:8px}
#chart{width:100%;height:300px;background:var(--card);border:1px solid var(--line);border-radius:8px}
#vovl{position:fixed;inset:0;background:rgba(1,4,9,.65);display:none;align-items:center;justify-content:center;z-index:55}
#vovl .vbox{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;width:min(760px,94vw);max-height:88vh;display:flex;flex-direction:column}
#vovl .chead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:14px}
#vovl #vbody{overflow-y:auto}
#vovl table{font-size:12px}
#covl{position:fixed;inset:0;background:rgba(1,4,9,.65);display:none;align-items:center;justify-content:center;z-index:60}
#covl .cbox{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;width:min(920px,94vw)}
#covl .chead{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:14px}
#cchart{width:100%;height:430px}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;margin-top:6px;color:var(--dim)}
.legend span{display:inline-flex;align-items:center;gap:4px}
.sw{width:10px;height:3px;display:inline-block;border-radius:2px}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;overflow-x:auto;color:var(--dim)}
.muted{color:var(--dim);font-size:12px}
button{cursor:pointer;background:#21262d;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:4px 14px;font:inherit;font-size:13px}
button:hover{background:#30363d}
button.danger{border-color:#6e2b28;color:var(--red)}
button.go{border-color:#2b5a30;color:var(--green)}
input{background:#0d1117;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:4px 10px;font:inherit;font-size:12px;width:200px}
.sq{width:22px;height:22px;padding:0;line-height:1;font-size:10px;border-radius:4px;color:var(--dim)}
.sq:hover{color:var(--red);border-color:#6e2b28}
.xwrap{display:inline-flex;gap:2px}
#xmenu{position:absolute;background:var(--card);border:1px solid var(--line);border-radius:6px;z-index:40;display:none;min-width:210px;box-shadow:0 8px 24px rgba(0,0,0,.5)}
#xmenu div{padding:7px 12px;cursor:pointer;font-size:13px}
#xmenu div:hover{background:#21262d}
#ovl{position:fixed;inset:0;background:rgba(1,4,9,.6);display:none;align-items:center;justify-content:center;z-index:50}
#ovl .box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 20px;max-width:440px;font-size:14px}
#ovl .box .bb{margin-top:14px;display:flex;gap:8px;justify-content:flex-end}
</style></head><body>
<h1>Paper Fleet</h1>
<div id="banner">loading…</div>
<div class="hero" id="hero"></div>
<div class="pills" id="pills"></div>
<div class="pills" id="controls"></div>
<div class="muted" id="ctlmsg"></div>
<h2>Open positions (live)</h2><div class="scroll"><table id="positions"></table></div>
<h2>Variants &amp; equity</h2>
<div class="pills" id="tabs"></div>
<div class="pills" id="range"></div>
<div id="chart"></div><div class="legend" id="legend"></div>
<div class="scroll" style="margin-top:8px"><table id="variants"></table></div>
<h2>Closed trades</h2><div class="scroll"><table id="trades"></table></div>
<h2>Pump events (regime dial inputs)</h2><div class="scroll"><table id="events"></table></div>
<h2>Phone alerts (ntfy)</h2>
<div class="pills" id="ntfy"></div>
<p class="muted">Get pushed: trade entries/exits (one alert per signal, not
per variant), kill-switch trips, cycle errors, fleet down/up. Setup: install
the free <b>ntfy</b> app (iOS/Android), subscribe to the topic above, hit
test. Anyone who knows the topic string can read these alerts — treat it
like a password (it contains no account info either way).</p>
<h2>Fleet log</h2><pre id="log"></pre>
<p class="muted" id="foot"></p>
<div id="xmenu"></div>
<div id="ovl"><div class="box"><div id="ovltext"></div>
<div class="bb"><button id="ovlcancel">Cancel</button>
<button class="danger" id="ovlgo">Close</button></div></div></div>
<div id="vovl"><div class="vbox"><div class="chead"><b id="vtitle"></b>
<button onclick="document.getElementById('vovl').style.display='none'">✕</button></div>
<div id="vbody"></div></div></div>
<div id="covl"><div class="cbox"><div class="chead"><b id="ctitle"></b>
<span class="pills" id="civ" style="margin:0"></span>
<button onclick="document.getElementById('covl').style.display='none'">✕</button></div>
<div id="cchart"></div>
<div class="muted">scroll left to load older history · drag to pan · wheel to zoom</div></div></div>
<script src="/lw.js"></script>
<script>
const COLORS=["#58a6ff","#3fb950","#f85149","#d29922","#bc8cff","#39c5cf",
"#ff7b72","#7ee787","#ffa657","#79c0ff","#d2a8ff","#56d4dd"];
const TZ=Intl.DateTimeFormat().resolvedOptions().timeZone;
const p2=n=>String(n).padStart(2,"0");
const fmt=t=>{const d=new Date(t);
  return `${p2(d.getMonth()+1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`};
const lt=t=>Math.floor(t/1000)-new Date(t).getTimezoneOffset()*60; // LW shows UTC; feed local-shifted
const pct=(v,d=2)=>v==null?"–":(v>0?"+":"")+v.toFixed(d)+"%";
const usd=v=>v==null?"–":(v<0?"−$":"+$")+Math.abs(v).toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g,",");
const cls=v=>v>0?"ok":v<0?"bad":"dim";
const left=t=>{const m=Math.round((t-Date.now())/60000);
  return m<=0?"closing…":m<60?m+"m":Math.floor(m/60)+"h "+(m%60)+"m";};
function esc(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}

function render(d){
  LAST=d;
  const g=d.gate,h=d.health,hero=d.hero;
  const bn=document.getElementById("banner");
  bn.className=h.status;
  bn.textContent=(h.status==="green"?"● ":"⚠ ")+h.msg;

  document.getElementById("hero").innerHTML=
    `<div class="stat"><div class="l">base P&amp;L (pre-registered short base)</div>
      <div class="v ${cls(hero.base_pnl)}">${usd(hero.base_pnl)}</div>
      <div class="s">${pct(hero.base_ret)} · ${hero.base_closed} closed · avg ${pct(hero.base_avg)} vs +${hero.bench}% benchmark</div></div>`+
    `<div class="stat"><div class="l">fleet total P&amp;L</div>
      <div class="v ${cls(hero.fleet_pnl)}">${usd(hero.fleet_pnl)}</div>
      <div class="s">${d.variants.length} × $10k accounts · ${hero.closed} closed trades</div></div>`+
    `<div class="stat"><div class="l">open / unrealized</div>
      <div class="v ${cls(hero.unreal)}">${usd(hero.unreal)}</div>
      <div class="s">${d.positions.length} open position${d.positions.length===1?"":"s"}</div></div>`+
    `<div class="stat"><div class="l">last 7 days</div>
      <div class="v ${cls(hero.week_pnl)}">${usd(hero.week_pnl)}</div>
      <div class="s">closed P&amp;L, all variants</div></div>`;

  const book=g.short?'<b class="bad">SHORT book open</b>':g.long?'<b class="ok">LONG book open</b>':'<b class="warn">all books FLAT</b>';
  const btc=g.bear==null?'<b class="warn">?</b>':g.bear?'<b class="bad">BEAR</b> (capit gate open)':'<b class="ok">BULL</b> (capit gate closed)';
  document.getElementById("pills").innerHTML=
    `<span class="pill">regime: ${book}</span>`+
    `<span class="pill">dial: n=${g.n}, mean 24h fwd <b class="${cls(g.m)}">${g.m==null?"n/a":pct(g.m*100)}</b></span>`+
    `<span class="pill">BTC 4h: ${btc}</span>`+
    `<span class="pill">lid-shut awake: <b class="${d.awake?"ok":"warn"}">${d.awake?"ON":"OFF"}</b></span>`+
    (d.paused?'<span class="pill"><b class="warn">TRADING PAUSED</b></span>':"")+
    `<span class="pill dim">updated ${new Date(d.now).toLocaleTimeString()}</span>`;

  document.getElementById("controls").innerHTML=(d.loaded
    ?`<button class="danger" onclick="ctl('fleet_stop')">&#9632; stop fleet</button>
      <button onclick="ctl('fleet_restart')">&#8635; restart</button>`
    :`<button class="go" onclick="ctl('fleet_start')">&#9654; start fleet</button>`)
    +(d.paused
    ?`<button class="go" onclick="ctl('pause_off')">&#9654; resume trading</button>`
    :`<button onclick="ctl('pause_on')">&#10074;&#10074; pause trading (keeps managing open positions)</button>`)
    +(d.awake
    ?`<button onclick="ctl('awake_off')">&#127769; allow sleep</button>`
    :`<button class="go" onclick="ctl('awake_on')">&#9728; keep awake (lid shut ok)</button>`);

  // open positions, marked to live price
  POS=d.positions;CMDQ=d.cmds||[];LOCAL=!!d.local;
  const closing=p=>CMDQ.some(c=>!c.type&&c.v===p.variant&&c.tk===p.ticker&&c.t_sig===p.t_sig);
  const tpq=p=>CMDQ.find(c=>c.type==="tp"&&c.v===p.variant&&c.tk===p.ticker&&c.t_sig===p.t_sig);
  let h2="<tr>"+(LOCAL?"<th></th>":"")+"<th>variant</th><th>ticker</th><th>side</th><th>entry</th><th>now</th><th>uP&amp;L</th><th>net</th><th>stop</th><th>tp</th><th>room to stop</th><th>time exit in</th><th>notional</th><th>since</th></tr>";
  if(!d.positions.length)h2+='<tr><td colspan="14" class="dim">none — scanning</td></tr>';
  d.positions.forEach((p,i)=>{
    const xc=!LOCAL?"":closing(p)
      ?'<td class="dim">closing…</td>'
      :`<td><span class="xwrap"><button class="sq" title="close now" onclick="mClose(${i})">&#9632;</button><button class="sq" title="exit method" onclick="xMenu(event,${i})">&#9662;</button></span></td>`;
    const q=tpq(p);
    const tpc=q?`<span class="dim">${q.tp==null?"clearing…":q.tp+"…"}</span>`
      :(p.tp!=null?p.tp:'<span class="dim">–</span>');
    h2+=`<tr>${xc}<td style="cursor:pointer" title="variant details" onclick="vModal('${p.variant}')">${p.variant}</td><td style="cursor:pointer" title="open chart" onclick="posChart(${i})"><b>${esc(p.ticker)}</b> <span class="dim">📈</span></td>
    <td class="${p.side==="short"?"bad":"ok"}">${p.side}</td>
    <td>${p.entry}</td><td>${p.px==null?"–":p.px}</td>
    <td class="${cls(p.upnl)}"><b>${usd(p.upnl)}</b></td>
    <td class="${cls(p.upct)}">${p.upct==null?"–":pct(p.upct*100)}</td>
    <td>${p.stop.toPrecision(6)}</td><td>${tpc}</td>
    <td class="${p.room!=null&&p.room<0.01?"bad":"dim"}">${p.room==null?"–":pct(p.room*100)}</td>
    <td>${left(p.exits_at)}</td><td>${p.notional.toFixed(0)}</td><td>${fmt(p.t_sig)}</td></tr>`;});
  document.getElementById("positions").innerHTML=h2;

  // strategy tabs filter both the variants table and the equity chart
  const vmap={};d.variants.forEach(v=>vmap[v.name]=v);
  const tabPnl=k=>{const names=k==="all"?d.variants.map(v=>v.name):d.strats[k].variants;
    return names.reduce((a,n)=>a+(vmap[n]?vmap[n].equity-10000:0),0);};
  let tabs=`<button class="${TAB==="all"?"go":""}" onclick="setTab('all')">all (${usd(tabPnl("all"))})</button>`;
  Object.entries(d.strats).forEach(([k,s])=>{
    const short=s.label.split("—")[0].trim();
    tabs+=`<button class="${TAB===k?"go":""}" onclick="setTab('${k}')">${esc(short)} · ${s.variants.length} (${usd(tabPnl(k))})</button>`;});
  document.getElementById("tabs").innerHTML=tabs;

  let shown=(TAB==="all"?d.variants
    :(d.strats[TAB]?d.strats[TAB].variants.map(n=>vmap[n]).filter(Boolean):d.variants)).slice();
  if(SORT.col){
    const k=SORT.col,dir=SORT.dir;
    const val=v=>k==="open"?v.open.length:k==="variant"?v.name:v[k];
    shown.sort((a,b)=>{const x=val(a),y=val(b);
      if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;
      return (x<y?-1:x>y?1:0)*dir;});
  }
  const arrow=k=>SORT.col===k?(SORT.dir>0?" ▲":" ▼"):"";
  const TH=(k,lab,left)=>`<th onclick="setSort('${k}')" style="cursor:pointer${left?";text-align:left":""}" title="click to sort">${lab}${arrow(k)}</th>`;
  let h3="<tr>"+TH("variant","variant",1)+TH("equity","equity")+TH("ret","ret")
    +TH("open","open")+TH("closed","closed")+TH("win","win")
    +TH("avg","avg net")+TH("bt","bt net")
    +"<th style='text-align:left'>params</th></tr>";
  if(TAB!=="all"&&d.strats[TAB])
    h3+=`<tr><td colspan="9" style="text-align:left" class="dim">${esc(d.strats[TAB].label)}</td></tr>`;
  shown.forEach(v=>{
    h3+=`<tr><td style="cursor:pointer" title="variant details" onclick="vModal('${v.name}')"><b>${v.name}</b>${v.kill?' <b class="bad">KILL</b>':''}</td><td>${v.equity.toFixed(2)}</td>`+
    `<td class="${cls(v.ret)}">${pct(v.ret)}</td><td>${v.open.length}</td><td>${v.closed}</td>`+
    `<td>${v.win==null?"–":v.win+"%"}</td><td class="${cls(v.avg)}">${pct(v.avg,3)}</td>`+
    `<td class="dim">${pct(v.bt)}</td><td style="text-align:left" class="dim">${esc(v.params)}</td></tr>`;});
  document.getElementById("variants").innerHTML=h3;

  // trades
  let h4="<tr><th>exit</th><th>variant</th><th>ticker</th><th>kind</th><th>net</th><th>pnl</th><th>notional</th><th>equity after</th></tr>";
  if(!d.trades.length)h4+='<tr><td colspan="8" class="dim">none yet</td></tr>';
  d.trades.forEach((t,i)=>{h4+=`<tr><td>${fmt(t.exit_t)}</td><td style="cursor:pointer" title="variant details" onclick="vModal('${t.variant}')">${t.variant}</td><td style="cursor:pointer" title="open chart" onclick="tradeChart(${i})"><b>${esc(t.ticker)}</b> <span class="dim">📈</span></td><td>${t.kind}</td><td class="${cls(t.net)}">${pct(t.net*100)}</td><td class="${cls(t.pnl)}">${t.pnl.toFixed(2)}</td><td>${t.notional.toFixed(0)}</td><td>${t.equity_after.toFixed(2)}</td></tr>`;});
  document.getElementById("trades").innerHTML=h4;

  // events
  let h5="<tr><th>time</th><th>ticker</th><th>price</th><th>24h fwd</th></tr>";
  d.events.forEach((e,i)=>{const f=e.dead?'<span class="dim">excluded</span>':e.fwd==null?'<span class="dim">pending</span>':`<span class="${cls(e.fwd)}">${pct(e.fwd*100)}</span>`;
    h5+=`<tr><td>${fmt(e.t)}</td><td style="cursor:pointer" title="open chart" onclick="eventChart(${i})"><b>${esc(e.tk)}</b> <span class="dim">📈</span></td><td>${e.px}</td><td>${f}</td></tr>`;});
  document.getElementById("events").innerHTML=h5;

  document.getElementById("ntfy").innerHTML=
    `<span class="pill">topic: <b>${esc(d.ntfy)||'<span class="warn">off</span>'}</b></span>`+
    `<button onclick="ctl('ntfy_test')">send test</button>`+
    `<input id="topicin" placeholder="new topic (blank = off)">`+
    `<button onclick="ctl('set_ntfy',{topic:document.getElementById('topicin').value})">save</button>`;

  document.getElementById("log").textContent=d.log.join("\\n")||"(empty)";
  document.getElementById("foot").textContent=
    `fleet since ${fmt(d.start)} · times in ${TZ} · auto-refresh 60s · controls work from this Mac only`;
  chart(d,shown);
}

let TAB="all",LAST=null,SORT={col:null,dir:-1};
function setTab(t){TAB=t;if(LAST)render(LAST);}
function vModal(name){
  const v=LAST&&LAST.variants.find(x=>x.name===name);
  if(!v)return;
  document.getElementById("vtitle").innerHTML=
    `${esc(name)} <span class="dim" style="font-weight:400">· ${esc(v.group||"")}</span>`;
  const stat=(l,val,c)=>`<div class="stat"><div class="l">${l}</div>`+
    `<div class="v${c?" "+c:""}" style="font-size:17px">${val}</div></div>`;
  let h=`<div class="hero" style="margin-bottom:8px">`
    +stat("equity","$"+v.equity.toFixed(2))
    +stat("return",pct(v.ret),cls(v.ret))
    +stat("closed / win",`${v.closed}${v.win==null?"":" / "+v.win+"%"}`)
    +stat("avg net",pct(v.avg,3),cls(v.avg))
    +stat("backtest",pct(v.bt,2))
    +`</div>`;
  if(v.kill)h+=`<p class="bad" style="margin:4px 0">kill-switch pause active</p>`;
  h+=`<p class="dim" style="font-size:12px;margin:4px 0">${esc(v.params)}</p>`;
  if(v.note)h+=`<p class="muted" style="margin:6px 0">${esc(v.note)}</p>`;
  h+=`<h2 style="margin:10px 0 6px">config</h2><table>`;
  Object.entries(v.cfg||{}).forEach(([k,val])=>{
    h+=`<tr><td style="text-align:left">${esc(k)}</td>`+
       `<td style="text-align:left" class="dim">${esc(JSON.stringify(val))}</td></tr>`;});
  h+=`</table>`;
  if(v.open.length){
    h+=`<h2 style="margin:10px 0 6px">open positions</h2><table>`+
       `<tr><th style="text-align:left">ticker</th><th>side</th><th>entry</th><th>now</th><th>unreal</th><th>exits</th></tr>`;
    v.open.forEach(p=>{h+=`<tr><td>${esc(p.ticker)}</td><td>${p.side}</td>`+
      `<td>${p.entry}</td><td>${p.px==null?"–":p.px}</td>`+
      `<td class="${cls(p.upct)}">${p.upct==null?"–":pct(p.upct*100)}</td>`+
      `<td>${left(p.exits_at)}</td></tr>`;});
    h+=`</table>`;}
  const tr=LAST.trades.filter(t=>t.variant===name).slice(0,10);
  if(tr.length){
    h+=`<h2 style="margin:10px 0 6px">recent trades</h2><table>`+
       `<tr><th style="text-align:left">exit</th><th style="text-align:left">ticker</th><th>kind</th><th>net</th><th>pnl</th><th>equity after</th></tr>`;
    tr.forEach(t=>{h+=`<tr><td style="text-align:left">${fmt(t.exit_t)}</td>`+
      `<td style="text-align:left">${esc(t.ticker)}</td><td>${t.kind}</td>`+
      `<td class="${cls(t.net)}">${pct(t.net*100)}</td>`+
      `<td class="${cls(t.pnl)}">${t.pnl.toFixed(2)}</td><td>${t.equity_after.toFixed(2)}</td></tr>`;});
    h+=`</table>`;}
  document.getElementById("vbody").innerHTML=h;
  document.getElementById("vovl").style.display="flex";
}
document.getElementById("vovl").onclick=e=>{
  if(e.target.id==="vovl")e.target.style.display="none";};
function setSort(c){
  if(SORT.col===c)SORT.dir=-SORT.dir;      // same column: flip direction
  else SORT={col:c,dir:c==="variant"?1:-1}; // numbers: big first; names: a-z
  if(LAST)render(LAST);
}

// ---- equity chart: lightweight-charts, pan/zoom/crosshair + ranges ----
const LWOPTS={layout:{background:{color:"transparent"},textColor:"#8b949e",fontSize:11},
  grid:{vertLines:{color:"#21262d"},horzLines:{color:"#21262d"}},
  timeScale:{timeVisible:true,secondsVisible:false,borderColor:"#30363d"},
  rightPriceScale:{borderColor:"#30363d"},
  crosshair:{mode:LightweightCharts.CrosshairMode.Normal},autoSize:true};
let LW=null,SERIES=[],RANGE=null;
function setRange(days){
  RANGE=days;
  if(!LW)return;
  if(days==null){LW.timeScale().fitContent();}
  else{const now=lt(Date.now());
    LW.timeScale().setVisibleRange({from:now-days*86400,to:now});}
  renderRange();
}
function renderRange(){
  document.getElementById("range").innerHTML=
    [["1D",1],["1W",7],["1M",30],["ALL",null]].map(([lab,d])=>
      `<button class="${RANGE===d?"go":""}" onclick="setRange(${d})">${lab}</button>`).join("");
}
function chart(d,shown){
  const el=document.getElementById("chart");
  if(!LW){LW=LightweightCharts.createChart(el,LWOPTS);renderRange();}
  SERIES.forEach(s=>LW.removeSeries(s));SERIES=[];
  const vs=shown&&shown.length?shown:d.variants;
  vs.forEach((v,i)=>{
    const s=LW.addLineSeries({color:COLORS[i%COLORS.length],lineWidth:2,
      priceLineVisible:false,lastValueVisible:false,
      crosshairMarkerVisible:true,title:v.name});
    let last=0;
    s.setData(v.curve.filter(c=>{const t=lt(c[0]);
      if(t<=last)return false;last=t;return true;})
      .map(c=>({time:lt(c[0]),value:c[1]})));
    SERIES.push(s);});
  setRange(RANGE);
  document.getElementById("legend").innerHTML=vs.map((v,i)=>
    `<span><i class="sw" style="background:${COLORS[i%COLORS.length]}"></i>${v.name} ${v.equity.toFixed(0)}</span>`).join("");
}

// ---- per-trade candle chart: entry/stop/tp lines, exit marker,
// ---- interval switcher, lazy back-load to the perp's listing date ----
let CW=null,CS=null,CK=[],CSYM=null,CO=null,CIV="15m",CLOADING=false,CMORE=true;
const IVMS={"15m":900000,"1h":3600000,"4h":14400000,"1d":86400000};
const snap=(t,iv)=>t-t%IVMS[iv];
function cset(){
  CS.setData(CK.map(c=>({time:lt(c.t),open:c.o,high:c.h,low:c.l,close:c.c})));
  const mk=[{time:lt(snap(CO.t_sig,CIV)),
    position:CO.side==="short"?"aboveBar":"belowBar",color:"#58a6ff",
    shape:CO.side==="short"?"arrowDown":"arrowUp",text:"in"}];
  if(CO.exit_t)mk.push({time:lt(snap(CO.exit_t,CIV)),position:"inBar",
    color:"#d29922",shape:"circle",text:CO.kind||"out"});
  CS.setMarkers(CK.length?mk.filter(m=>m.time>=lt(CK[0].t)):[]);
}
async function cfetch(params){
  const qs=Object.entries(params).map(([k,v])=>`${k}=${encodeURIComponent(v)}`).join("&");
  const r=await fetch(`/candles?symbol=${encodeURIComponent(CSYM)}&interval=${CIV}&${qs}`);
  return await r.json();
}
async function cload(){
  CLOADING=true;CMORE=true;
  const iv=IVMS[CIV],now=Date.now();
  let k;
  if(CO.exit_t){
    const start=snap(CO.t_sig,CIV)-60*iv;
    const limit=Math.min(Math.ceil((CO.exit_t-start)/iv)+40,1500);
    k=await cfetch({start,limit});
  }else{
    k=await cfetch({limit:420});
  }
  CK=k;cset();CW.timeScale().fitContent();CLOADING=false;
}
async function colder(){
  if(CLOADING||!CMORE||!CK.length)return;
  CLOADING=true;
  const k=await cfetch({end:CK[0].t-1,limit:1000});
  if(!k.length)CMORE=false;
  else CK=k.concat(CK.filter(c=>c.t>k[k.length-1].t));
  cset();CLOADING=false;
}
function civ(iv){CIV=iv;renderCiv();cload();}
function renderCiv(){
  document.getElementById("civ").innerHTML=
    Object.keys(IVMS).map(iv=>
      `<button class="${CIV===iv?"go":""}" onclick="civ('${iv}')">${iv}</button>`).join("");
}
async function openChart(sym,title,o){
  document.getElementById("ctitle").textContent=title;
  document.getElementById("covl").style.display="flex";
  const el=document.getElementById("cchart");
  if(CW){CW.remove();}
  CW=LightweightCharts.createChart(el,LWOPTS);
  CS=CW.addCandlestickSeries({upColor:"#3fb950",downColor:"#f85149",
    wickUpColor:"#3fb950",wickDownColor:"#f85149",borderVisible:false});
  const line=(px,col,lab)=>px&&CS.createPriceLine({price:px,color:col,
    lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:lab});
  line(o.entry,"#58a6ff","entry");
  if(o.stop)line(o.stop,"#f85149","stop");
  if(o.tp)line(o.tp,"#3fb950","tp");
  CSYM=sym;CO=o;CIV="15m";renderCiv();
  CW.timeScale().subscribeVisibleLogicalRangeChange(r=>{
    if(r&&r.from<30)colder();});
  await cload();
}
function posChart(i){
  const p=POS[i];
  openChart(LAST.symbols[p.ticker],
    `${p.ticker} ${p.side} — ${p.variant} (open, ${usd(p.upnl)})`,
    {t_sig:p.t_sig,entry:p.entry,stop:p.stop>0?p.stop:null,tp:p.tp,side:p.side});
}
function tradeChart(i){
  const t=LAST.trades[i];
  openChart(LAST.symbols[t.ticker],
    `${t.ticker} — ${t.variant} (closed ${t.kind}, ${pct(t.net*100)})`,
    {t_sig:t.t_sig,entry:t.entry,stop:t.stop>0?t.stop:null,
     exit_t:t.exit_t,kind:t.kind,side:null});
}
function eventChart(i){
  const e=LAST.events[i];
  const done=e.fwd!=null&&!e.dead;
  openChart(LAST.symbols[e.tk],
    `${e.tk} — pump event (dial input${done?", 24h fwd "+pct(e.fwd*100):e.dead?", excluded":", pending"})`,
    {t_sig:e.t,entry:e.px,stop:null,
     exit_t:done?e.t+86400000:null,kind:"24h",side:"short"});
}
document.getElementById("covl").addEventListener("click",e=>{
  if(e.target.id==="covl")e.target.style.display="none";});

async function ctl(action,extra){
  const el=document.getElementById("ctlmsg");
  el.textContent="working…";
  try{
    const r=await fetch("/ctl",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action,...(extra||{})})});
    const d=await r.json();
    el.textContent=d.ok?("done"+(d.msg?" — "+d.msg:"")):"failed: "+d.msg;
  }catch(e){el.textContent="failed: "+e;}
  setTimeout(tick,1500);
  setTimeout(()=>{el.textContent=""},10000);
}

async function tick(){
  try{const r=await fetch("/api");render(await r.json());}
  catch(e){const bn=document.getElementById("banner");bn.className="red";
    bn.textContent="⚠ dashboard server unreachable";}
}
// ---- exits: square = close now; caret = exit method (tp / time) ----
let POS=[],CMDQ=[],LOCAL=false;
const ovl=document.getElementById("ovl"),menu=document.getElementById("xmenu");
function showModal(text,cb,input){
  document.getElementById("ovltext").innerHTML=text
    +(input?`<div style="margin-top:10px"><input id="ovlin" placeholder="${input.ph}" value="${input.val||""}"></div>`:"");
  ovl.style.display="flex";
  const go=document.getElementById("ovlgo"),ca=document.getElementById("ovlcancel");
  go.textContent=input?"Set":"Close";
  go.onclick=()=>{const v=input?document.getElementById("ovlin").value.trim():null;
    ovl.style.display="none";cb(v);};
  ca.onclick=()=>ovl.style.display="none";
  if(input){const f=document.getElementById("ovlin");f.focus();
    f.onkeydown=e=>{if(e.key==="Enter")go.onclick();};}
  else ca.focus();
}
ovl.addEventListener("click",e=>{if(e.target===ovl)ovl.style.display="none";});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){ovl.style.display="none";menu.style.display="none";document.getElementById("covl").style.display="none";}});
document.addEventListener("click",e=>{if(!menu.contains(e.target)&&!e.target.classList.contains("sq"))menu.style.display="none";});
async function send(action,body){
  menu.style.display="none";
  await ctl(action,body);
  tick();
}
const ref=p=>({v:p.variant,tk:p.ticker,t_sig:p.t_sig});
function mClose(i){
  const p=POS[i];
  showModal(`Close <b>${esc(p.ticker)} ${p.side}</b> (${p.variant}) now? Fills at the fleet's next cycle. Est. P&amp;L <b class="${cls(p.upnl)}">${usd(p.upnl)}</b>.`,
    ()=>send("close",ref(p)));
}
function mTp(i){
  const p=POS[i];
  const hint=p.side==="long"?"above":"below";
  showModal(`Take-profit for <b>${esc(p.ticker)} ${p.side}</b> (${p.variant}): exits when price touches the level. Must be ${hint} entry ${p.entry}. Time exit stays as fallback.`,
    v=>{const tp=parseFloat(v);
      if(!(tp>0)){document.getElementById("ctlmsg").textContent="bad tp price";return;}
      send("tp",{...ref(p),tp});},
    {ph:`price (${hint} ${p.entry})`,val:p.tp!=null?p.tp:""});
}
function xMenu(ev,i){
  ev.stopPropagation();
  const p=POS[i];
  menu.innerHTML=
    `<div onclick="mClose(${i})">Close now (market)</div>`+
    `<div onclick="mTp(${i})">${p.tp!=null?"Change":"Set"} take-profit price…</div>`+
    (p.tp!=null?`<div onclick='showModal("Clear take-profit on <b>${esc(p.ticker)}</b>? Back to the default time exit.",()=>send("tp",{v:"${p.variant}",tk:"${p.ticker}",t_sig:${p.t_sig},tp:null}))'>Clear take-profit (${p.tp})</div>`:"")+
    `<div class="dim" style="cursor:default">default: time exit ${left(p.exits_at)}</div>`;
  menu.style.display="block";
  menu.style.left=Math.min(ev.pageX,window.innerWidth-230)+"px";
  menu.style.top=ev.pageY+4+"px";
}

tick();setInterval(tick,60000);
addEventListener("resize",()=>tick());
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api":
            d = payload()
            d["local"] = self.client_address[0] in ("127.0.0.1", "::1")
            body = json.dumps(d).encode()
            ctype = "application/json"
        elif path == "/lw.js":
            body, ctype = LWJS, "application/javascript"
        elif path == "/candles":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            sym = q.get("symbol", [""])[0]
            iv = q.get("interval", ["15m"])[0]
            if sym not in UNI.values() or iv not in IVALS:
                self.send_error(404)
                return
            try:
                start = int(q.get("start", ["0"])[0]) or None
                end = int(q.get("end", ["0"])[0]) or None
                limit = max(10, min(int(q.get("limit", ["400"])[0]), 1500))
            except ValueError:
                self.send_error(400)
                return
            body = json.dumps(fetch_candles(sym, iv, limit, start,
                                            end)).encode()
            ctype = "application/json"
        elif path == "/":
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/ctl":
            self.send_error(404)
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_error(403)         # controls from this Mac only
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            action = body.get("action")
        except Exception:
            body, action = {}, None
        if action not in ACTIONS:
            self.send_error(400)
            return
        ok, msg = ACTIONS[action](body)
        if not ok and action.startswith("awake") and "sudo" in msg.lower():
            msg = AWAKE_HELP
        out = json.dumps(dict(ok=ok, msg=msg)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):           # keep stdout quiet
        pass


def main():
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    port = int(OPS.get("dashboard_port", 8787))
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    ensure_ntfy()
    threading.Thread(target=watchdog, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"fleet dashboard: http://{'localhost' if host != '0.0.0.0' else host}:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
