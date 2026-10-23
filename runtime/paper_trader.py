#!/usr/bin/env python3
"""Live paper trader for rule P (pump-short), per reports/rules_preregistration.md.

Polls Binance USDT-M futures 15m candles, evaluates the frozen pump-short rule
at candle close, and simulates fills with the same fee/portfolio model as
rules_backtest.py. No real orders are placed.

Signal (on a closed 15m candle): 4h run-up >= +12%, close < previous close,
volume >= 2x mean of prior 8 candles, gapless/alive tape.
Entry: short at signal close. Stop: new high above the signal-time 4h high.
Time exit: 16 candles (4h). Fees: 2x taker 0.045% + 0.05% slip per round trip.
Portfolio: 0.75% equity risk per trade, 20% notional cap, max 6 concurrent,
one per ticker, kill-switch 7d -5% -> 3d pause. Paper equity starts at $10,000.

Restart-safe: open positions replay their exits from candle history, so
downtime never corrupts an open trade. Signals are only taken on the most
recent closed candle, so entries missed while down are skipped, not backfilled.

Usage: python3 paper_trader.py            # poll loop (15m cadence)
       python3 paper_trader.py --once     # one cycle, then exit
       python3 paper_trader.py --status   # print state and recent trades
Files: paper/state.json, paper/trades_paper.csv, paper/paper.log
"""
import csv
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from core.backtest import DEFAULTS as _MODEL

M15 = 900_000

# Trade model — fees, sizing, starting equity. Single source of truth is
# core.backtest.DEFAULTS, so live/paper and the backtester never drift apart.
TAKER = _MODEL["taker"]
SLIP = _MODEL["slip"]
RISK = _MODEL["risk"]
NOTIONAL_CAP = _MODEL["notional_cap"]
START_EQUITY = _MODEL["start_equity"]

# Live-fleet operational params (no backtest equivalent): concurrency + kill-switch.
MAX_CONC = 6
KILL_DD = -0.05
KILL_LOOKBACK = 7 * 86_400_000
KILL_PAUSE = 3 * 86_400_000

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper")
STATE = os.path.join(DIR, "state.json")
TRADES = os.path.join(DIR, "trades_paper.csv")
LOG = os.path.join(DIR, "paper.log")
API = "https://fapi.binance.com/fapi/v1/klines"


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%m-%d %H:%M")


def klines(symbol, limit=25, start=None):
    url = f"{API}?symbol={symbol}&interval=15m&limit={limit}"
    if start is not None:
        url += f"&startTime={start}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                rows = json.loads(r.read())
            now = int(time.time() * 1000)
            return [dict(t=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]),
                         c=float(r[4]), v=float(r[5]))
                    for r in rows if int(r[6]) <= now]  # closed candles only
        except Exception as e:
            if attempt == 2:
                log(f"WARN {symbol}: fetch failed ({e})")
                return None
            time.sleep(2 * (attempt + 1))


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return dict(equity=START_EQUITY, kill_until=0, last_sig_t=0,
                positions=[], eq_hist=[])


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def record_trade(row):
    new = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ticker", "t_sig", "entry", "stop", "exit_t", "kind",
                        "net", "pnl", "notional", "equity_after"])
        w.writerow(row)


def check_exit(pos, candles):
    """Replay post-signal candles. Mirrors exit_P in rules_backtest.py."""
    entry, stop = pos["entry"], pos["stop"]
    post = [k for k in candles if k["t"] >= pos["t_sig"]][:16]
    for n, k in enumerate(post, 1):
        if k["h"] > stop:
            net = -(stop / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "sl"
        if n == 16:
            net = -(k["c"] / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "time"
    return None


def signal_P(k):
    """Rule P on the last closed candle of a 25-candle history."""
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:        # gapless 4h
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < 0.12 or k[i]["c"] >= k[i - 1]["c"]:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < 2:
        return None
    stop = max(x["h"] for x in k[i - 16:i + 1])
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"], stop=stop, runup=runup)


def cycle(universe, st):
    # 1) replay exits for open positions
    for pos in list(st["positions"]):
        cnd = klines(pos["symbol"], limit=20, start=pos["t_sig"])
        if cnd is None:
            continue
        ex = check_exit(pos, cnd)
        if ex is None:
            continue
        net, exit_t, kind = ex
        pnl = pos["notional"] * net
        st["equity"] += pnl
        st["eq_hist"].append([exit_t, st["equity"]])
        st["positions"].remove(pos)
        record_trade([pos["ticker"], pos["t_sig"], pos["entry"], pos["stop"],
                      exit_t, kind, round(net, 6), round(pnl, 2),
                      round(pos["notional"], 2), round(st["equity"], 2)])
        log(f"EXIT {pos['ticker']} {kind} net {net*100:+.2f}% pnl {pnl:+.2f} "
            f"equity {st['equity']:.2f}")

    # 2) scan for new signals on the latest closed candle
    open_tk = {p["ticker"] for p in st["positions"]}
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = dict(zip(universe, ex.map(
            lambda tk: klines(universe[tk]), universe)))
    max_t = st["last_sig_t"]
    for tk, cnd in results.items():
        if cnd is None or not cnd:
            continue
        sig = signal_P(cnd)
        if sig is None:
            continue
        max_t = max(max_t, sig["t_sig"])
        if sig["t_sig"] <= st["last_sig_t"]:
            continue                                   # already processed
        if tk in open_tk:
            log(f"SKIP {tk}: position already open")
            continue
        if len(st["positions"]) >= MAX_CONC:
            log(f"SKIP {tk}: {MAX_CONC} positions open")
            continue
        if sig["t_sig"] < st["kill_until"]:
            log(f"SKIP {tk}: kill-switch pause until {iso(st['kill_until'])}")
            continue
        hist = [e for e in st["eq_hist"] if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
        if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
            st["kill_until"] = sig["t_sig"] + KILL_PAUSE
            log(f"KILL-SWITCH: 7d drawdown < -5%, pausing until {iso(st['kill_until'])}")
            continue
        sl_dist = sig["stop"] / sig["entry"] - 1
        notional = min(RISK * st["equity"] / max(abs(sl_dist), 0.005),
                       NOTIONAL_CAP * st["equity"])
        st["positions"].append(dict(ticker=tk, symbol=universe[tk],
                                    t_sig=sig["t_sig"], entry=sig["entry"],
                                    stop=sig["stop"], notional=notional))
        open_tk.add(tk)
        log(f"ENTER SHORT {tk} @ {sig['entry']} (runup {sig['runup']*100:+.1f}%) "
            f"stop {sig['stop']} ({sl_dist*100:+.1f}%) notional {notional:.2f}")
    st["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 2 * KILL_LOOKBACK]
    save_state(st)


def status():
    st = load_state()
    print(f"equity: {st['equity']:.2f} (start {START_EQUITY:.0f})")
    print(f"open positions: {len(st['positions'])}")
    for p in st["positions"]:
        print(f"  {p['ticker']} short @ {p['entry']} stop {p['stop']} "
              f"notional {p['notional']:.2f} since {iso(p['t_sig'])}")
    if st["kill_until"] > time.time() * 1000:
        print(f"kill-switch active until {iso(st['kill_until'])}")
    if os.path.exists(TRADES):
        rows = list(csv.reader(open(TRADES)))[1:]
        print(f"closed trades: {len(rows)}")
        for r in rows[-10:]:
            print(f"  {r[0]:10s} {r[5]:4s} net {float(r[6])*100:+.2f}% "
                  f"pnl {float(r[7]):+.2f} eq {r[9]}")


def main():
    os.makedirs(DIR, exist_ok=True)
    universe = json.load(open(os.path.join(DIR, "universe60.json")))
    if "--status" in sys.argv:
        return status()
    st = load_state()
    log(f"paper trader start | equity {st['equity']:.2f} | "
        f"{len(st['positions'])} open | universe {len(universe)}")
    while True:
        try:
            cycle(universe, st)
        except Exception as e:
            log(f"ERROR cycle: {e!r}")
        if "--once" in sys.argv:
            break
        now = time.time()
        nxt = (now // 900 + 1) * 900 + 30          # 30s after candle close
        time.sleep(max(nxt - now, 1))


if __name__ == "__main__":
    main()
