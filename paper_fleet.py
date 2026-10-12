#!/usr/bin/env python3
"""Fleet of paper traders — every strategy variant in fleet_config.json
(short and long books), all in one process sharing one candle fetch per
cycle.

Each variant is an independent paper account: own $10,000 equity, own
positions, own kill-switch, own trade log. Rule shape and fee/portfolio
model are identical to rules_backtest.py; only the labeled parameter differs.

Variants (backtest net/trade over the 7 walk-forward windows in parens):
  base    frozen gate-passing rule: runup>=12%, vol>=2x, hold 4h, stop 4h high (+3.41%)
  loose   runup >= 8%   — failed the backtest (+0.86%); live canary, ~10 trades/mo
  strict  runup >= 16%  (+6.46%, ~1.5/mo)
  vol3    volume >= 3x  (+8.04%, ~1/mo)
  fast    hold 2h  (+2.61%)
  slow    hold 8h  (+3.65%)
  hold24  hold 24h (+3.58%)
  buf2    stop = 4h high + 2% buffer (+3.39%)
  trail3  trailing stop: lowest low since entry + 3x NATR24, seeded at 4h high (+3.18%)

Usage: python3 paper_fleet.py            # poll loop (15m cadence)
       python3 paper_fleet.py --once     # one cycle, then exit
       python3 paper_fleet.py --monitor  # live dashboard for all variants
       python3 paper_fleet.py --status   # dashboard once, no refresh
Files: paper/fleet/<variant>.json, paper/fleet/trades_<variant>.csv, paper/fleet/fleet.log
"""
import csv
import fcntl
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import regime
from paper_trader import klines, M15, TAKER, SLIP, RISK, NOTIONAL_CAP, \
    MAX_CONC, KILL_DD, KILL_LOOKBACK, KILL_PAUSE, START_EQUITY, API

# Strategy + variant definitions live in fleet_config.json ("strategies"
# section — fingerprinted: changes are logged and phone-alerted so the paper
# record always shows when the rules moved). This builds the same VARIANTS
# shape the engine always used.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fleet_config.json")
try:
    CFG = json.load(open(CONFIG_PATH))
except FileNotFoundError:
    sys.exit(f"missing {CONFIG_PATH} — the strategy/ops config is required")
OPS = CFG.get("ops", {})

VARIANTS, BT, STRATS = {}, {}, {}
for _sk, _s in CFG["strategies"].items():
    _names = []
    for _vn, _v in _s["variants"].items():
        if not _v.get("enabled", True):
            continue
        _cfg = {k: v for k, v in _v.items()
                if k not in ("bt", "note", "enabled")}
        _cfg["stop"] = tuple(_cfg["stop"])
        VARIANTS[_vn] = _cfg
        BT[_vn] = _v.get("bt")
        _names.append(_vn)
    STRATS[_sk] = dict(label=_s.get("label", _sk), variants=_names)

# Regime gate (gate30): short only when the pump dial is negative; momentum
# LONG book (ts30) only when it is > +2%. Spec, thresholds and the dial
# machinery live in regime.py — these aliases keep the fleet's public names
# (hl_bot imports them). Backtest evidence: gated shorts +2.48%/trade vs
# +1.08% ungated (reports/regime_policy_*.txt); two-sided +1.75%/trade,
# +48.7% compounded (reports/twosided_system_*.txt). Not pre-registered.
GATE_WINDOW = regime.WINDOW_MS
GATE_MIN_EV = regime.MIN_EV
GATE_FWD = regime.FWD_BARS_15M            # 24h in 15m bars
GATE_COOLDOWN = regime.COOLDOWN_MS
GATE_LONG_THR = regime.LONG_THR
MOMO_VOL = 2.5
MOMO_HOLD = 48           # 12h

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper", "fleet")
LOG = os.path.join(DIR, "fleet.log")


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%m-%d %H:%M")


def natr24_1h(symbol):
    """NATR24 from 1h candles, matching rules_backtest.load: mean 24h true
    range / close, on the last closed candle. None on fetch failure."""
    url = f"{API}?symbol={symbol}&interval=1h&limit=27"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        k = [(float(x[2]), float(x[3]), float(x[4]))
             for x in rows if int(x[6]) <= now]      # closed (h, l, c)
        if len(k) < 25:
            return None
        k = k[-25:]
        trs = [max(k[j][0], k[j - 1][2]) - min(k[j][1], k[j - 1][2])
               for j in range(1, 25)]
        return (sum(trs) / 24) / k[-1][2]
    except Exception:
        return None


def spath(name):
    return os.path.join(DIR, f"{name}.json")


def tpath(name):
    return os.path.join(DIR, f"trades_{name}.csv")


def load_state(name):
    if os.path.exists(spath(name)):
        st = json.load(open(spath(name)))
        st.setdefault("orders", [])
        return st
    return dict(equity=START_EQUITY, kill_until=0, last_sig_t=0,
                positions=[], eq_hist=[], orders=[])


def save_state(name, st):
    tmp = f"{spath(name)}.tmp.{os.getpid()}"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, spath(name))


def record_trade(name, row):
    new = not os.path.exists(tpath(name))
    with open(tpath(name), "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ticker", "t_sig", "entry", "stop", "exit_t", "kind",
                        "net", "pnl", "notional", "equity_after"])
        w.writerow(row)


EVENTS = os.path.join(DIR, "pump_events.json")
CMDS = os.path.join(DIR, "commands.json")  # dashboard close-trade queue
PAUSE = os.path.join(DIR, "PAUSED")       # touch = no new entries (exits run)
NTFY_CFG = os.path.join(DIR, "ntfy.json")  # {"topic": "...", "enabled": true}
NOTES = []                                 # per-cycle buffer -> one push/event
_pause_state = [None]


def ntfy_topic():
    try:
        c = json.load(open(NTFY_CFG))
        return c.get("topic") if c.get("enabled", True) and c.get("topic") \
            else None
    except Exception:
        return None


def notify(title, msg, priority="default", tags=None, cat=None):
    """Push to the phone via ntfy.sh. Fire-and-forget; never blocks a cycle.
    cat maps to ops.alerts.<cat> in fleet_config.json (default on)."""
    if cat and not OPS.get("alerts", {}).get(cat, True):
        return
    topic = ntfy_topic()
    if not topic:
        return
    def _send():
        try:
            hdrs = {"Title": title, "Priority": priority}
            if tags:
                hdrs["Tags"] = tags
            req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                         data=msg.encode(), headers=hdrs)
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


def flush_notes():
    """Aggregate the cycle's trade events into one push each — a signal fires
    across ~11 variants at once; nobody wants 11 notifications."""
    if not NOTES:
        return
    enters = {}
    for n in (x for x in NOTES if x["kind"] == "enter"):
        enters.setdefault((n["tk"], n["side"]), []).append(n)
    for (tk, side), ns in enters.items():
        word = "LONG" if side == 1 else "SHORT"
        notify(f"ENTER {word} {tk} @ {ns[0]['px']}",
               f"runup {ns[0]['runup']*100:+.1f}% | {len(ns)} variants: "
               + ", ".join(x["v"] for x in ns),
               priority="high", cat="entries",
               tags="chart_with_upwards_trend" if side == 1
               else "chart_with_downwards_trend")
    exits = {}
    for n in (x for x in NOTES if x["kind"] == "exit"):
        exits.setdefault(n["tk"], []).append(n)
    for tk, ns in exits.items():
        tot = sum(x["pnl"] for x in ns)
        notify(f"EXIT {tk} {'WIN' if tot > 0 else 'LOSS'} ${tot:+,.0f}",
               ", ".join(f"{x['v']} {x['net']*100:+.1f}%" for x in ns),
               priority="high", cat="exits",
               tags="moneybag" if tot > 0 else "small_red_triangle_down")
    for n in (x for x in NOTES if x["kind"] == "kill"):
        notify(f"KILL-SWITCH: {n['v']}",
               "7d drawdown < -5% — variant paused for 3 days",
               priority="urgent", tags="rotating_light", cat="kill_switch")
    NOTES.clear()


def load_events():
    if os.path.exists(EVENTS):
        return json.load(open(EVENTS))
    return dict(events=[], last_ev={})


def save_events(store):
    tmp = f"{EVENTS}.tmp.{os.getpid()}"
    json.dump(store, open(tmp, "w"))
    os.replace(tmp, EVENTS)


def detect_events(store, candles):
    """Pump events (no weakness/vol filter) on the last closed candle —
    detection logic in regime.detect_pump_event; store/log owned here."""
    for tk, k in candles.items():
        ev = regime.detect_pump_event(k, store["last_ev"].get(tk, -10**18))
        if ev is None:
            continue
        store["events"].append(dict(tk=tk, t=ev["t"], px=ev["px"],
                                    fwd=None, tries=0))
        store["last_ev"][tk] = ev["t"]
        log(f"[gate] pump event {tk} @ {ev['px']} "
            f"(+{ev['runup'] * 100:.1f}%/4h)")


def resolve_events(store, universe):
    """Fill in 24h forward returns once events mature. Lazy, one fetch each."""
    now = int(time.time() * 1000)
    for ev in store["events"]:
        if ev["fwd"] is not None or ev.get("dead") or ev["tries"] >= 5:
            continue
        done_t = ev["t"] + GATE_FWD * M15
        if now < done_t + 2 * M15 or ev["tk"] not in universe:
            continue
        ev["tries"] += 1
        k = klines(universe[ev["tk"]], limit=2, start=done_t)
        if not k:
            continue
        if k[0]["t"] != done_t:
            ev["dead"] = True            # gap/delist — excluded, like backtest
            continue
        ev["fwd"] = k[0]["c"] / ev["px"] - 1
    store["events"] = [e for e in store["events"]
                       if e["t"] >= now - GATE_WINDOW - 5 * 86_400_000]


def gate_state(store):
    """-> dict(short, long, n, m). Short when m < 0; long when m > +2%."""
    return regime.gate_state(store["events"])


def signal(k, cfg):
    """Pump-short signal on the last closed candle. Base cfg == rule P frozen."""
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:        # gapless 4h
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < cfg["runup"] or k[i]["c"] >= k[i - 1]["c"]:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < cfg["vol"]:
        return None
    if cfg.get("wick"):
        O = k[i - 15]["o"]
        Hh = max(x["h"] for x in k[i - 15:i + 1])
        Ll = min(x["l"] for x in k[i - 15:i + 1])
        rng = Hh - Ll
        if rng <= 0 or (Hh - max(O, k[i]["c"])) / rng < cfg["wick"]:
            return None
    hh = max(x["h"] for x in k[i - 16:i + 1])
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"], hh=hh, runup=runup)


def signal_capit(k, cfg):
    """Capitulation LONG on the last closed candle (capit_long strategy):
    24h return <= -depth on FRESH crossing (newly true this bar), gapless
    24h tape. Mirrors gen_signals(trig='r24') in long_rules_backtest.py.
    Returns sl_basis = max(2*NATR24, 0.5%) — the sizing basis used by the
    backtests (there is no real stop in the 'none' stop mode)."""
    if len(k) < 98:
        return None
    i = len(k) - 1

    def cond(j):
        if j < 97:
            return False
        if k[j]["t"] - k[j - 96]["t"] != 96 * M15:     # gapless 24h
            return False
        if any(x["v"] <= 0 for x in k[j - 8:j + 1]) or k[j]["h"] == k[j]["l"]:
            return False
        return k[j]["c"] / k[j - 96]["c"] - 1 <= -cfg["depth"]

    if not cond(i) or cond(i - 1):                     # fresh crossing only
        return None
    trs = [max(k[j]["h"], k[j - 1]["c"]) - min(k[j]["l"], k[j - 1]["c"])
           for j in range(i - 95, i + 1)]
    natr = (sum(trs) / 96) / k[i]["c"]
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"],
                runup=k[i]["c"] / k[i - 96]["c"] - 1,
                sl_basis=max(2 * natr, 0.005))


_btc_cache = [0.0, None]


def btc_bear():
    """True when BTC 4h EMA20 <= EMA50 (bear), matching btc_regime() in
    long_robustness.py (bull is strictly EMA20 > EMA50 on the last CLOSED
    4h candle). None on fetch failure — treated as gate closed. 10m cache."""
    if time.time() - _btc_cache[0] < 600 and _btc_cache[1] is not None:
        return _btc_cache[1]
    url = f"{API}?symbol=BTCUSDT&interval=4h&limit=200"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        closes = [float(x[4]) for x in rows if int(x[6]) <= now]
        if len(closes) < 60:
            return _btc_cache[1]
        _btc_cache[0], _btc_cache[1] = time.time(), not regime.ema_bull(closes)
        return _btc_cache[1]
    except Exception:
        return _btc_cache[1]


def signal_momo(k):
    """Momentum-continuation LONG on the last closed candle (ts30 long book):
    runup>=12%/4h, vol>=2.5x, synthetic-4h upper wick<=15%, close in top 20%.
    Mirrors sigs_long_momo in indicator_tests.py."""
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < 0.12:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < MOMO_VOL:
        return None
    O = k[i - 15]["o"]
    Hh = max(x["h"] for x in k[i - 15:i + 1])
    Ll = min(x["l"] for x in k[i - 15:i + 1])
    C = k[i]["c"]
    rng = Hh - Ll
    if rng <= 0:
        return None
    if (Hh - max(O, C)) / rng > 0.15 or (C - Ll) / rng < 0.80:
        return None
    stop = max(Ll, (O + C) / 2) * 0.999
    return dict(t_sig=k[i]["t"] + M15, entry=C, stop=stop, runup=runup)


def check_exit(pos, candles):
    """Replay post-signal candles. Mirrors exit_g in holds_stops_backtest.py:
    check stop breach first, then (trail mode) ratchet the level down.
    side -1 = short (default, stop above), +1 = long (stop below)."""
    entry, hold = pos["entry"], pos["hold"]
    side = pos.get("side", -1)
    level, low_min = pos["stop"], entry
    trail_k = pos.get("trail_k")
    natr = pos.get("natr")
    tp = pos.get("tp")
    post = [k for k in candles if k["t"] >= pos["t_sig"]][:hold]
    for n, k in enumerate(post, 1):
        if (k["h"] > level) if side < 0 else (k["l"] < level):
            net = side * (level / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "sl"
        if tp and ((k["l"] <= tp) if side < 0 else (k["h"] >= tp)):
            net = side * (tp / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "tp"
        if side < 0 and trail_k and natr:
            low_min = min(low_min, k["l"])
            level = min(level, low_min * (1 + trail_k * natr))
        if n == hold:
            net = side * (k["c"] / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "time"
    return None


def run_exits(name, st):
    for pos in list(st["positions"]):
        cnd = klines(pos["symbol"], limit=min(pos["hold"] + 8, 250),
                     start=pos["t_sig"])
        if cnd is None:
            continue
        ex = check_exit(pos, cnd)
        if ex is None:
            continue
        net, exit_t, kind = ex
        pnl = pos["notional"] * net
        if pos.get("margin"):
            # isolated-margin floor: a position can never lose more than
            # its posted margin (the super engine's disaster bound)
            pnl = max(pnl, -pos["margin"])
        st["equity"] += pnl
        st["eq_hist"].append([exit_t, st["equity"]])
        st["positions"].remove(pos)
        record_trade(name, [pos["ticker"], pos["t_sig"], pos["entry"],
                            pos["stop"], exit_t, kind, round(net, 6),
                            round(pnl, 2), round(pos["notional"], 2),
                            round(st["equity"], 2)])
        log(f"[{name}] EXIT {pos['ticker']} {kind} net {net*100:+.2f}% "
            f"pnl {pnl:+.2f} equity {st['equity']:.2f}")
        if not VARIANTS[name].get("quiet"):
            NOTES.append(dict(kind="exit", v=name, tk=pos["ticker"],
                              net=net, pnl=pnl))


def run_churn(name, st, universe, candles):
    """Churn engine: at most one entry per `every` bars — fade the largest
    1h move across the whole universe (short the top gainer, long the top
    loser, |move| >= min_move), stop at the 1h extreme, time exit after
    cfg hold. High-frequency: live fill/cost/beta data at ~hourly pace."""
    cfg = VARIANTS[name]
    best = None
    for tk, k in candles.items():
        if not k or len(k) < 6:
            continue
        i = len(k) - 1
        if k[i]["t"] - k[i - 4]["t"] != 4 * M15:
            continue
        if any(x["v"] <= 0 for x in k[i - 4:i + 1]) or k[i]["h"] == k[i]["l"]:
            continue
        mv = k[i]["c"] / k[i - 4]["c"] - 1
        if abs(mv) < cfg.get("min_move", 0.01):
            continue
        if best is None or abs(mv) > abs(best[1]):
            best = (tk, mv, k)
    if best is None:
        return
    tk, mv, k = best
    i = len(k) - 1
    t_sig = k[i]["t"] + M15
    if t_sig <= st["last_sig_t"] \
            or t_sig - st["last_sig_t"] < cfg.get("every", 4) * M15:
        return
    if tk in {p["ticker"] for p in st["positions"]}:
        return
    if len(st["positions"]) >= MAX_CONC:
        return
    if t_sig < st["kill_until"]:
        return
    hist = [e for e in st["eq_hist"] if e[0] >= t_sig - KILL_LOOKBACK]
    if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
        st["kill_until"] = t_sig + KILL_PAUSE
        log(f"[{name}] KILL-SWITCH: 7d drawdown < -5%, pause until "
            f"{iso(st['kill_until'])}")
        NOTES.append(dict(kind="kill", v=name))
        return
    side = -1 if mv > 0 else 1
    entry = k[i]["c"]
    stop = (max(x["h"] for x in k[i - 4:i + 1]) if side == -1
            else min(x["l"] for x in k[i - 4:i + 1]))
    sl_dist = stop / entry - 1
    notional = min(RISK * st["equity"] / max(abs(sl_dist), 0.005),
                   NOTIONAL_CAP * st["equity"])
    st["positions"].append(dict(ticker=tk, symbol=universe[tk], t_sig=t_sig,
                                entry=entry, stop=stop, notional=notional,
                                hold=cfg["hold"], side=side))
    st["last_sig_t"] = t_sig
    log(f"[{name}] ENTER {'LONG' if side == 1 else 'SHORT'} {tk} @ {entry} "
        f"(1h move {mv*100:+.1f}%) stop {stop:.6g} ({sl_dist*100:+.1f}%) "
        f"notional {notional:.2f}")
    if not cfg.get("quiet"):
        NOTES.append(dict(kind="enter", v=name, tk=tk, side=side,
                          px=entry, runup=mv))
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 2 * KILL_LOOKBACK]


def run_loser(name, st, universe, candles):
    """Hourly long-loser engine: every `every` bars, LONG the biggest 1h
    loser across the universe if its move <= -min_move. No stop, time exit
    after `hold`. Same-ticker re-entry each hour is allowed BY DESIGN
    (averaging into a persistent dump is ~half the backtest edge); `slots`
    caps concurrency and each entry's notional = equity/slots. Mirrors the
    thr/hold collect() in hourly_loser_diligence.py (bt +0.694%/trade)."""
    cfg = VARIANTS[name]
    worst = None
    for tk, k in candles.items():
        if not k or len(k) < 6:
            continue
        i = len(k) - 1
        if k[i]["t"] - k[i - 4]["t"] != 4 * M15:
            continue
        if any(x["v"] <= 0 for x in k[i - 4:i + 1]) or k[i]["h"] == k[i]["l"]:
            continue
        mv = k[i]["c"] / k[i - 4]["c"] - 1
        if worst is None or mv < worst[1]:
            worst = (tk, mv, k)
    if worst is None:
        return
    tk, mv, k = worst
    if mv > -cfg.get("min_move", 0.02):
        return
    i = len(k) - 1
    t_sig = k[i]["t"] + M15
    if t_sig <= st["last_sig_t"] \
            or t_sig - st["last_sig_t"] < cfg.get("every", 4) * M15:
        return
    slots = cfg.get("slots", 12)
    if len(st["positions"]) >= slots:
        log(f"[{name}] SKIP {tk}: {slots} slots full")
        st["last_sig_t"] = t_sig
        return
    if t_sig < st["kill_until"]:
        return
    hist = [e for e in st["eq_hist"] if e[0] >= t_sig - KILL_LOOKBACK]
    if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
        st["kill_until"] = t_sig + KILL_PAUSE
        log(f"[{name}] KILL-SWITCH: 7d drawdown < -5%, pause until "
            f"{iso(st['kill_until'])}")
        NOTES.append(dict(kind="kill", v=name))
        return
    entry = k[i]["c"]
    notional = st["equity"] / slots
    st["positions"].append(dict(ticker=tk, symbol=universe[tk], t_sig=t_sig,
                                entry=entry, stop=0.0, notional=notional,
                                hold=cfg["hold"], side=1))
    st["last_sig_t"] = t_sig
    log(f"[{name}] ENTER LONG {tk} @ {entry} (1h move {mv*100:+.1f}%) "
        f"no stop, hold {cfg['hold']*15//60}h, notional {notional:.2f}")
    if not cfg.get("quiet"):
        NOTES.append(dict(kind="enter", v=name, tk=tk, side=1,
                          px=entry, runup=mv))
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 2 * KILL_LOOKBACK]


LIMIT_WINDOW = 16        # bars a resting limit entry stays working (4h)


def run_orders(name, st, universe, candles):
    """Resting limit entries (capit `limit` variants). An order placed at
    signal time fills when a later CLOSED candle's low trades through the
    limit price (fill at the limit, like the backtest's intra-bar fill),
    and is cancelled once LIMIT_WINDOW bars have closed without a touch.
    Mirrors make_exit(limit=...) in capit_variants2_backtest.py. Orders
    fill even while trading is paused — they model orders already resting
    on the exchange."""
    if not st.get("orders"):
        return
    cfg = VARIANTS[name]
    now = int(time.time() * 1000)
    for od in list(st["orders"]):
        cnd = candles.get(od["ticker"])
        window_end = od["t_sig"] + LIMIT_WINDOW * M15
        fill_bar = None
        if cnd:
            for k in cnd:
                if od["t_sig"] <= k["t"] < window_end and k["l"] <= od["limit"]:
                    fill_bar = k
                    break
        if fill_bar is None:
            closed_past = (cnd and cnd[-1]["t"] >= window_end) \
                or now > window_end + 2 * M15
            if closed_past:
                st["orders"].remove(od)
                log(f"[{name}] CANCEL {od['ticker']}: limit {od['limit']:.6g} "
                    f"not touched in {LIMIT_WINDOW} bars")
            continue
        st["orders"].remove(od)
        if od["ticker"] in {p["ticker"] for p in st["positions"]}:
            log(f"[{name}] CANCEL {od['ticker']}: position already open at fill")
            continue
        if len(st["positions"]) >= MAX_CONC:
            log(f"[{name}] CANCEL {od['ticker']}: {MAX_CONC} positions open at fill")
            continue
        if fill_bar["t"] + M15 < st["kill_until"]:
            log(f"[{name}] CANCEL {od['ticker']}: kill-switch pause")
            continue
        notional = min(RISK * st["equity"] / max(od["sl_basis"], 0.005),
                       NOTIONAL_CAP * st["equity"])
        pos = dict(ticker=od["ticker"], symbol=od["symbol"],
                   t_sig=fill_bar["t"] + M15, entry=od["limit"], stop=0.0,
                   notional=notional, hold=cfg["hold"], side=1)
        st["positions"].append(pos)
        log(f"[{name}] FILL LONG {od['ticker']} @ {od['limit']:.6g} "
            f"(limit -{cfg['limit']*100:.0f}% of {od['sig_px']:.6g}) "
            f"notional {notional:.2f}")
        NOTES.append(dict(kind="enter", v=name, tk=od["ticker"], side=1,
                          px=od["limit"], runup=od.get("runup", 0.0)))


def run_signals(name, st, universe, candles, natr_cache, gate=None):
    cfg = VARIANTS[name]
    mode, parm = cfg["stop"]
    open_tk = {p["ticker"] for p in st["positions"]} \
        | {o["ticker"] for o in st.get("orders", [])}
    max_t = st["last_sig_t"]
    for tk, cnd in candles.items():
        if not cnd:
            continue
        if cfg.get("only") and tk not in cfg["only"]:
            continue
        side = -1
        if cfg.get("engine") == "capit":
            sig = signal_capit(cnd, cfg)
            side = 1
        elif cfg.get("engine") == "momo":
            sig = signal_momo(cnd)
            side = 1
        elif cfg.get("engine") == "super":
            # Super Larry: two legs, one account. S = pump short (hold24,
            # gate30-gated), C = capit long (48h, no stop, btc-bear-gated).
            s_sig = signal(cnd, cfg)
            c_sig = signal_capit(cnd, cfg)
            sig = None
            if s_sig:
                if gate and gate["short"]:
                    sig = dict(s_sig, leg="S")
                else:
                    max_t = max(max_t, s_sig["t_sig"])
                    if s_sig["t_sig"] > st["last_sig_t"]:
                        g = gate or dict(n=0, m=None)
                        m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
                        log(f"[{name}] SKIP {tk}: S-leg regime gate closed "
                            f"(n={g['n']}, m={m})")
            if sig is None and c_sig:
                if gate and gate.get("bear") is True:
                    sig, side = dict(c_sig, leg="C"), 1
                else:
                    max_t = max(max_t, c_sig["t_sig"])
                    if c_sig["t_sig"] > st["last_sig_t"]:
                        log(f"[{name}] SKIP {tk}: C-leg — BTC not in bear regime")
            if sig is None:
                continue
        elif cfg.get("twosided"):
            s_sig = signal(cnd, cfg)
            m_sig = signal_momo(cnd)
            if s_sig and gate and gate["short"]:
                sig = s_sig
            elif m_sig and gate and gate["long"]:
                sig, side = m_sig, 1
            elif s_sig or m_sig:
                sig = s_sig or m_sig
                max_t = max(max_t, sig["t_sig"])
                if sig["t_sig"] > st["last_sig_t"]:
                    g = gate or dict(n=0, m=None)
                    m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
                    book = "short" if s_sig else "long"
                    log(f"[{name}] SKIP {tk}: {book} book closed "
                        f"(n={g['n']}, m={m})")
                continue
            else:
                continue
        else:
            sig = signal(cnd, cfg)
        if sig is None:
            continue
        max_t = max(max_t, sig["t_sig"])
        if sig["t_sig"] <= st["last_sig_t"]:
            continue
        if cfg.get("btc_bear") and not (gate and gate.get("bear") is True):
            why = ("BTC data unavailable" if not gate or gate.get("bear")
                   is None else "BTC not in bear regime")
            log(f"[{name}] SKIP {tk}: {why}")
            continue
        if cfg.get("gate"):
            book = "long" if side == 1 else "short"
            if not (gate and gate[book]):
                g = gate or dict(n=0, m=None)
                m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
                log(f"[{name}] SKIP {tk}: regime gate — {book} book closed "
                    f"(n={g['n']}, m={m})")
                continue
        if cfg.get("veto"):
            # regime VETO: skip only when the dial is decisively hostile
            # (> threshold); trade when negative, flat or unknown
            m = gate.get("m") if gate else None
            if m is not None and m == m and m > cfg["veto"]:
                log(f"[{name}] SKIP {tk}: regime veto — dial {m*100:+.2f}% "
                    f"> +{cfg['veto']*100:.0f}%")
                continue
        if tk in open_tk:
            log(f"[{name}] SKIP {tk}: position already open")
            continue
        if cfg.get("conc"):
            legn = sig.get("leg", "S")
            if sum(1 for q in st["positions"]
                   if q.get("leg") == legn) >= cfg["conc"][legn]:
                log(f"[{name}] SKIP {tk}: {cfg['conc'][legn]} {legn}-leg positions open")
                continue
        elif len(st["positions"]) >= MAX_CONC:
            log(f"[{name}] SKIP {tk}: {MAX_CONC} positions open")
            continue
        if sig["t_sig"] < st["kill_until"]:
            log(f"[{name}] SKIP {tk}: kill-switch pause until {iso(st['kill_until'])}")
            continue
        hist = [e for e in st["eq_hist"] if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
        if not cfg.get("no_kill") and hist \
                and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
            st["kill_until"] = sig["t_sig"] + KILL_PAUSE
            log(f"[{name}] KILL-SWITCH: 7d drawdown < -5%, pause until {iso(st['kill_until'])}")
            NOTES.append(dict(kind="kill", v=name))
            continue
        if cfg.get("engine") == "capit" and cfg.get("limit"):
            limit_px = sig["entry"] * (1 - cfg["limit"])
            st["orders"].append(dict(ticker=tk, symbol=universe[tk],
                                     t_sig=sig["t_sig"], limit=limit_px,
                                     sig_px=sig["entry"], runup=sig["runup"],
                                     sl_basis=sig.get("sl_basis", 0.02)))
            open_tk.add(tk)
            log(f"[{name}] ORDER {tk}: resting limit {limit_px:.6g} "
                f"(-{cfg['limit']*100:.0f}% of signal close {sig['entry']:.6g}, "
                f"{LIMIT_WINDOW}-bar window)")
            continue
        natr = None
        if mode == "trail":
            if tk not in natr_cache:
                natr_cache[tk] = natr24_1h(universe[tk])
            natr = natr_cache[tk]
            if natr is None:
                log(f"[{name}] WARN {tk}: NATR fetch failed, stop stays at 4h high")
        if cfg.get("engine") == "super":
            # C leg: no stop (rug risk bounded by the margin cap);
            # S leg: signal-window 4h high
            stop = 0.0 if sig.get("leg") == "C" else sig["hh"] * (1 + parm)
        elif cfg.get("engine") == "capit":
            # "none" = no stop (level 0 is never hit on a long);
            # "dstop" = disaster stop parm below entry
            stop = 0.0 if mode == "none" else sig["entry"] * (1 - parm)
        elif side == 1:
            stop = sig["stop"]
        else:
            stop = sig["hh"] * (1 + parm) if mode == "hh" else sig["hh"]
        sl_dist = stop / sig["entry"] - 1
        margin = None
        if cfg.get("sizing"):
            # frac-of-equity margin at leverage, scaled to signal strength
            # (runup/threshold for S, drop/depth for C), capped. Loss is
            # floored at -margin in run_exits (isolated-margin semantics).
            legn = sig.get("leg", "S")
            b_, lv_, pw_, cap_ = cfg["sizing"][legn]
            ref = cfg["runup"] if legn == "S" else cfg["depth"]
            frac = min(b_ * (abs(sig["runup"]) / ref) ** pw_, cap_)
            margin = frac * st["equity"]
            notional = margin * lv_
        else:
            # capit sizes on 2*NATR24 (sl_basis), matching the backtests —
            # a stop at 0 is not a sizing basis
            size_basis = sig.get("sl_basis", abs(sl_dist))
            notional = min(RISK * st["equity"] / max(size_basis, 0.005),
                           NOTIONAL_CAP * st["equity"])
        hold = MOMO_HOLD if side == 1 and cfg.get("twosided") else cfg["hold"]
        if cfg.get("engine") == "super" and sig.get("leg") == "C":
            hold = cfg.get("c_hold", cfg["hold"])
        pos = dict(ticker=tk, symbol=universe[tk], t_sig=sig["t_sig"],
                   entry=sig["entry"], stop=stop, notional=notional,
                   hold=hold, side=side)
        if margin is not None:
            pos.update(margin=round(margin, 2), leg=sig.get("leg", "S"))
        if mode == "trail" and side == -1:
            pos.update(trail_k=parm, natr=natr)
        st["positions"].append(pos)
        open_tk.add(tk)
        log(f"[{name}] ENTER {'LONG' if side == 1 else 'SHORT'} {tk} "
            f"@ {sig['entry']} (runup {sig['runup']*100:+.1f}%) "
            f"stop {stop:.6g} ({sl_dist*100:+.1f}%) notional {notional:.2f}")
        NOTES.append(dict(kind="enter", v=name, tk=tk, side=side,
                          px=sig["entry"], runup=sig["runup"]))
    st["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 2 * KILL_LOOKBACK]


def run_books(name, st, universe, candles, gate):
    """Portfolio engine: several books, one shared account. Each book has
    its own rule (kind: pump/capit/loser), ticker filter (only), gates,
    hold, cap (conc, or slots for loser) and risk_w weight. One position
    per ticker account-wide, except the loser book may re-enter a ticker
    it already holds (averaging into the dump is that edge). Account-level
    kill-switch; standard risk sizing x risk_w (no margin ladder)."""
    cfg = VARIANTS[name]
    bstates = st.setdefault("books", {})
    now = int(time.time() * 1000)
    for bname, b in cfg["books"].items():
        bs = bstates.setdefault(bname, dict(last_sig_t=0))
        uni = {tk: c for tk, c in candles.items()
               if c and (not b.get("only") or tk in b["only"])}
        cands = []
        if b["kind"] == "loser":
            worst = None
            for tk, k in uni.items():
                if len(k) < 6:
                    continue
                i = len(k) - 1
                if k[i]["t"] - k[i - 4]["t"] != 4 * M15:
                    continue
                if any(x["v"] <= 0 for x in k[i - 4:i + 1]) \
                        or k[i]["h"] == k[i]["l"]:
                    continue
                mv = k[i]["c"] / k[i - 4]["c"] - 1
                if worst is None or mv < worst[1]:
                    worst = (tk, mv, k)
            if worst and worst[1] <= -b.get("min_move", 0.02):
                tk, mv, k = worst
                t_sig = k[-1]["t"] + M15
                if t_sig - bs["last_sig_t"] >= b.get("every", 4) * M15:
                    cands.append((tk, dict(t_sig=t_sig, entry=k[-1]["c"],
                                           runup=mv), 1))
        else:
            for tk, k in uni.items():
                if b["kind"] == "capit":
                    sig, side = signal_capit(k, b), 1
                else:
                    sig, side = signal(k, b), -1
                if sig is not None:
                    cands.append((tk, sig, side))
        max_t = bs["last_sig_t"]
        for tk, sig, side in cands:
            if sig["t_sig"] <= bs["last_sig_t"]:
                continue
            max_t = max(max_t, sig["t_sig"])
            if b.get("btc_bear") and not (gate and gate.get("bear") is True):
                log(f"[{name}] SKIP {tk} ({bname}): BTC not in bear regime")
                continue
            if b.get("gate"):
                book_dir = "long" if side == 1 else "short"
                if not (gate and gate[book_dir]):
                    g = gate or dict(n=0, m=None)
                    m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
                    log(f"[{name}] SKIP {tk} ({bname}): regime gate closed "
                        f"(n={g['n']}, m={m})")
                    continue
            blockers = {p["ticker"] for p in st["positions"]
                        if b["kind"] != "loser" or p.get("book") != bname}
            if tk in blockers:
                log(f"[{name}] SKIP {tk} ({bname}): ticker already held")
                continue
            n_book = sum(1 for p in st["positions"]
                         if p.get("book") == bname)
            cap = b.get("slots") or b.get("conc", MAX_CONC)
            if n_book >= cap:
                log(f"[{name}] SKIP {tk} ({bname}): {cap} positions open")
                continue
            if sig["t_sig"] < st["kill_until"]:
                continue
            hist = [e for e in st["eq_hist"]
                    if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
            if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
                st["kill_until"] = sig["t_sig"] + KILL_PAUSE
                log(f"[{name}] KILL-SWITCH: 7d drawdown < -5%, pause until "
                    f"{iso(st['kill_until'])}")
                NOTES.append(dict(kind="kill", v=name))
                continue
            risk_w = b.get("risk_w", 1.0)
            if b["kind"] == "loser":
                stop = 0.0
                notional = risk_w * st["equity"] / b.get("slots", 8)
            elif b["kind"] == "capit":
                stop = 0.0
                basis = sig.get("sl_basis", 0.02)
                notional = risk_w * min(
                    RISK * st["equity"] / max(basis, 0.005),
                    NOTIONAL_CAP * st["equity"])
            else:
                stop = sig["hh"]
                basis = abs(stop / sig["entry"] - 1)
                notional = risk_w * min(
                    RISK * st["equity"] / max(basis, 0.005),
                    NOTIONAL_CAP * st["equity"])
            pos = dict(ticker=tk, symbol=universe[tk], t_sig=sig["t_sig"],
                       entry=sig["entry"], stop=stop,
                       notional=round(notional, 2), hold=b["hold"],
                       side=side, book=bname)
            st["positions"].append(pos)
            log(f"[{name}] ENTER {'LONG' if side == 1 else 'SHORT'} {tk} "
                f"({bname}) @ {sig['entry']} (move {sig['runup']*100:+.1f}%) "
                f"stop {stop:.6g} notional {notional:.2f}")
            NOTES.append(dict(kind="enter", v=name, tk=tk, side=side,
                              px=sig["entry"], runup=sig["runup"]))
        bs["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= now - 2 * KILL_LOOKBACK]


def load_cmds():
    try:
        return json.load(open(CMDS))
    except Exception:
        return []


def save_cmds(cmds):
    tmp = f"{CMDS}.tmp.{os.getpid()}"
    json.dump(cmds, open(tmp, "w"))
    os.replace(tmp, CMDS)


def apply_cmd(cmd, states, candles):
    """One dashboard command. type=tp sets/clears a take-profit level on a
    position (price-side exit, honored by check_exit); default is a manual
    close, filled at this cycle's last closed candle and logged kind=manual
    so rule P&L and override P&L never mix. Returns False when a targeted
    close has no candle yet (retry next cycle)."""
    if cmd.get("type") == "tp":
        st = states.get(cmd.get("v"))
        if st is not None:
            for pos in st["positions"]:
                if pos["ticker"] != cmd.get("tk") \
                        or pos["t_sig"] != cmd.get("t_sig"):
                    continue
                tp, side = cmd.get("tp"), pos.get("side", -1)
                if tp is None:
                    pos.pop("tp", None)
                    log(f"[{cmd['v']}] TP CLEARED {pos['ticker']} "
                        "(back to time exit)")
                elif (tp > pos["entry"]) if side == 1 else (tp < pos["entry"]):
                    pos["tp"] = tp
                    log(f"[{cmd['v']}] TP SET {pos['ticker']} @ {tp:.6g} "
                        f"(entry {pos['entry']:.6g}, "
                        f"{side * (tp / pos['entry'] - 1) * 100:+.1f}%)")
                else:
                    log(f"[{cmd['v']}] TP REJECTED {pos['ticker']}: {tp:.6g} "
                        f"not on the profit side of entry {pos['entry']:.6g}")
        return True
    scope = cmd.get("scope")
    targets = [(n, st) for n, st in states.items()
               if scope == "all" or cmd.get("v") == n]
    done = True
    for name, st in targets:
        for pos in list(st["positions"]):
            if scope == "trade" and not (pos["ticker"] == cmd.get("tk")
                                         and pos["t_sig"] == cmd.get("t_sig")):
                continue
            k = candles.get(pos["ticker"])
            if not k:
                done = False
                continue
            px, t_x = k[-1]["c"], k[-1]["t"] + M15
            side = pos.get("side", -1)
            net = side * (px / pos["entry"] - 1) - (2 * TAKER + SLIP)
            pnl = pos["notional"] * net
            if pos.get("margin"):
                pnl = max(pnl, -pos["margin"])
            st["equity"] += pnl
            st["eq_hist"].append([t_x, st["equity"]])
            st["positions"].remove(pos)
            record_trade(name, [pos["ticker"], pos["t_sig"], pos["entry"],
                                pos["stop"], t_x, "manual", round(net, 6),
                                round(pnl, 2), round(pos["notional"], 2),
                                round(st["equity"], 2)])
            log(f"[{name}] MANUAL EXIT {pos['ticker']} @ {px} "
                f"net {net*100:+.2f}% pnl {pnl:+.2f} equity {st['equity']:.2f}")
            NOTES.append(dict(kind="exit", v=name, tk=pos["ticker"],
                              net=net, pnl=pnl))
        for od in list(st.get("orders", [])):
            if scope == "trade" and od["ticker"] != cmd.get("tk"):
                continue
            st["orders"].remove(od)
            log(f"[{name}] MANUAL CANCEL resting order {od['ticker']}")
    return done


def run_commands(states, candles):
    cmds = load_cmds()
    if not cmds:
        return
    leftover = [c for c in cmds if not apply_cmd(c, states, candles)]
    for name, st in states.items():
        save_state(name, st)
    save_cmds(leftover)


def cycle(universe, states):
    # 110 bars: capit needs a gapless 24h lookback (96) + fresh-cross margin
    with ThreadPoolExecutor(max_workers=6) as ex:
        candles = dict(zip(universe, ex.map(
            lambda tk: klines(universe[tk], limit=110), universe)))
    n_ok = sum(1 for c in candles.values() if c)
    if n_ok < len(universe) * 0.8:
        log(f"WARN: only {n_ok}/{len(universe)} tickers fetched, skipping cycle")
        return
    store = load_events()
    detect_events(store, candles)
    resolve_events(store, universe)
    save_events(store)
    gate = gate_state(store)
    gate["bear"] = btc_bear()
    paused = os.path.exists(PAUSE)
    if paused != _pause_state[0]:
        if _pause_state[0] is not None or paused:
            log("trading PAUSED — no new entries; open positions still managed"
                if paused else "trading RESUMED")
            notify("Fleet " + ("paused" if paused else "resumed"),
                   "no new entries; open positions still managed" if paused
                   else "scanning for new entries again", cat="pause",
                   tags="pause_button" if paused else "arrow_forward")
        _pause_state[0] = paused
    natr_cache = {}
    for name, st in states.items():
        run_exits(name, st)
        run_orders(name, st, universe, candles)
        if not paused:
            if VARIANTS[name].get("engine") == "churn":
                run_churn(name, st, universe, candles)
            elif VARIANTS[name].get("engine") == "loser":
                run_loser(name, st, universe, candles)
            elif VARIANTS[name].get("engine") == "books":
                run_books(name, st, universe, candles, gate)
            else:
                run_signals(name, st, universe, candles, natr_cache, gate)
        save_state(name, st)
    run_commands(states, candles)        # dashboard manual closes, last word
    flush_notes()


def pstr(cfg):
    mode, parm = cfg["stop"]
    if cfg.get("engine") == "books":
        return "PORTFOLIO: " + " | ".join(
            f"{bn}({b['kind']}"
            + (f",{len(b['only'])}tk" if b.get("only") else "")
            + (",gated" if b.get("gate") or b.get("btc_bear") else "")
            + f",w{b.get('risk_w', 1.0):g})"
            for bn, b in cfg["books"].items())
    if cfg.get("engine") == "churn":
        return (f"fade biggest 1h mover >={cfg.get('min_move', 0.01)*100:g}% "
                f"every {cfg.get('every', 4)*15}m hold={cfg['hold']*15}m "
                "stop=1h-extreme")
    if cfg.get("engine") == "super":
        s_, c_ = cfg["sizing"]["S"], cfg["sizing"]["C"]
        return (f"SUPER: S pump>={cfg['runup']*100:.0f}% hold={cfg['hold']*15//60}h "
                f"{s_[1]:g}x quad-size c{s_[3]*100:.0f} +gate | "
                f"C capit-{cfg['depth']*100:.0f}% hold={cfg.get('c_hold', 192)*15//60}h "
                f"{c_[1]:g}x c{c_[3]*100:.0f} +btc-bear | margin-floored")
    if cfg.get("engine") == "loser":
        return (f"long biggest 1h loser <=-{cfg.get('min_move', 0.02)*100:g}% "
                f"every {cfg.get('every', 4)*15}m hold={cfg['hold']*15//60}h "
                f"no-stop {cfg.get('slots', 12)}-slot")
    if cfg.get("engine") == "capit":
        stop = "none" if mode == "none" else f"-{parm*100:.0f}% disaster"
        return (f"capit-long drop<=-{cfg['depth']*100:.0f}%/24h "
                f"hold={cfg['hold']*15//60}h stop={stop}"
                + (f" limit-{cfg['limit']*100:.0f}%" if cfg.get("limit") else "")
                + (" +btc-bear" if cfg.get("btc_bear") else " ungated")
                + (f" {len(cfg['only'])}-majors" if cfg.get("only") else ""))
    stop = {"hh": f"hh+{parm*100:.0f}%" if parm else "4h-high",
            "trail": f"trail{parm:g}natr",
            "sig": "signal-level"}[mode]
    return ((f"momo-long " if cfg.get("engine") == "momo" else "")
            + f"runup>={cfg['runup']*100:.0f}% vol>={cfg['vol']:g}x "
            f"hold={cfg['hold']*15//60}h stop={stop}"
            + (" +regime-gate" if cfg.get("gate") else "")
            + (f" +veto>{cfg['veto']*100:g}%" if cfg.get("veto") else "")
            + (" two-sided" if cfg.get("twosided") else ""))


def dashboard():
    lines = [f"PAPER FLEET   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"]
    lines.append(f"{'variant':8s} {'equity':>10s} {'ret%':>7s} {'open':>4s} "
                 f"{'closed':>6s} {'win%':>5s} {'avg net':>8s} {'bt net':>7s}  params")
    bt = {k: v or 0 for k, v in BT.items()}   # from fleet_config.json
    g = gate_state(load_events())
    m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
    books = ("SHORT book open" if g["short"] else
             "LONG book open" if g["long"] else "all books FLAT")
    lines.append(f"regime gate: {books} (30d events n={g['n']}, "
                 f"mean 24h fwd {m}; short m<0, long m>+2%)")
    open_rows = []
    for name, cfg in VARIANTS.items():
        st = load_state(name)
        trades = []
        if os.path.exists(tpath(name)):
            trades = [r for r in list(csv.reader(open(tpath(name))))[1:]
                      if r and r[0] != "ticker"]   # tolerate stray header rows
        nets = [float(r[6]) for r in trades]
        win = sum(1 for n in nets if n > 0) / len(nets) * 100 if nets else 0
        avg = sum(nets) / len(nets) * 100 if nets else 0
        ret = (st["equity"] / START_EQUITY - 1) * 100
        kill = " KILL" if st["kill_until"] > time.time() * 1000 else ""
        lines.append(f"{name:8s} {st['equity']:10.2f} {ret:+6.2f}% "
                     f"{len(st['positions']):4d} {len(trades):6d} {win:4.0f}% "
                     f"{avg:+7.3f}% {bt.get(name, 0):+6.2f}%  {pstr(cfg)}{kill}")
        for p in st["positions"]:
            sd = "long" if p.get("side", -1) == 1 else "short"
            open_rows.append(f"  [{name}] {p['ticker']} {sd} @ {p['entry']} "
                             f"stop {p['stop']:.6g} since {iso(p['t_sig'])}")
    if open_rows:
        lines.append("")
        lines.append("open positions:")
        lines += open_rows
    if os.path.exists(LOG):
        with open(LOG) as f:
            tail = f.readlines()[-8:]
        lines.append("")
        lines.append("recent activity:")
        lines += ["  " + ln.rstrip() for ln in tail]
    return "\n".join(lines)


def monitor():
    try:
        while True:
            print("\033[2J\033[H" + dashboard(), flush=True)
            time.sleep(60)
    except KeyboardInterrupt:
        pass


def main():
    known = {"--once", "--monitor", "--status"}
    bad = [a for a in sys.argv[1:] if a not in known]
    if bad:
        # A mistyped flag once fell through here and silently ran a SECOND
        # fleet loop (duplicate trades, tmp-file races). Never again.
        sys.exit(f"unknown argument(s): {' '.join(bad)} — valid: "
                 + " ".join(sorted(known)))
    os.makedirs(DIR, exist_ok=True)
    universe = json.load(open(os.path.join(
        os.path.dirname(DIR), "universe60.json")))
    if "--monitor" in sys.argv:
        return monitor()
    if "--status" in sys.argv:
        return print(dashboard())
    lock = open(os.path.join(DIR, "fleet.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another fleet instance is already running "
                 "(paper/fleet/fleet.lock is held) — refusing to start")
    lock.write(str(os.getpid()))
    lock.flush()
    # Strategy fingerprint: hash the loaded PARAMS (labels/notes/bt excluded)
    # and log + alert on change, so the trade record shows when rules moved.
    import hashlib
    fp_src = {k: dict(v, stop=list(v["stop"])) for k, v in VARIANTS.items()}
    fp = hashlib.sha256(json.dumps(fp_src,
                                   sort_keys=True).encode()).hexdigest()[:12]
    fp_path = os.path.join(DIR, "strategy_fingerprint.txt")
    old_fp = open(fp_path).read().strip() if os.path.exists(fp_path) else None
    if old_fp and old_fp != fp:
        log(f"STRATEGY CONFIG CHANGED: fingerprint {old_fp} -> {fp} "
            f"(fleet_config.json strategies section)")
        notify("Strategy config CHANGED",
               f"fingerprint {old_fp} → {fp} — paper results before/after "
               "this point are not comparable", priority="high",
               tags="warning")
    with open(fp_path, "w") as f:
        f.write(fp)
    states = {name: load_state(name) for name in VARIANTS}
    log(f"fleet start | {len(VARIANTS)} variants | universe {len(universe)} | "
        + " ".join(f"{n}={s['equity']:.0f}" for n, s in states.items()))
    last_err_note = 0
    while True:
        try:
            cycle(universe, states)
        except Exception as e:
            import traceback
            log(f"ERROR cycle: {e!r} | {traceback.format_exc().splitlines()[-3]}")
            if time.time() - last_err_note > 1800:   # max 1 push / 30 min
                last_err_note = time.time()
                notify("Fleet cycle ERROR", repr(e), priority="high",
                       tags="warning", cat="errors")
        if "--once" in sys.argv:
            break
        now = time.time()
        nxt = (now // 900 + 1) * 900 + 30
        time.sleep(max(nxt - now, 1))


if __name__ == "__main__":
    main()
