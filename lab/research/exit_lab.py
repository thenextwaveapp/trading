#!/usr/bin/env python3
"""Exit lab — entries held FIXED, exit policies swept, both books.

Short book: frozen rule P entries (runup>=12%/4h, first red, vol>=2x),
native stop at the 4h high kept in every policy. Long book: capit entries
(24h ret <= -20% fresh crossing, BTC-bear-gated), no native stop (matching
the deployed anchor). Exits swept on top:

  time N        pure time exit (baselines)
  tp X          take-profit at a fixed % from entry (limit-fill convention)
  retrace f     (short) cover when price gives back fraction f of the pump
  rsi T         exit when 15m RSI(14) crosses the threshold (close fill)
  sig_after a   (short) cover on first GREEN close once profit >= a
                (long)  sell on first RED close once profit >= a
  ema_state     (long) wait until close > EMA20, then exit on close < EMA20
  be_lock a     stop moves to entry once profit has reached a
  chand k       chandelier trail: favorable extreme +/- k * NATR24(entry)
  climax a      exit into a 3x-volume candle in your favor once profit >= a

Costs, sizing, portfolio layer identical to the other backtests.
Usage: python3 exit_lab.py
Writes: reports/exit_lab_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from regime_switch_backtest import load_full, WINDOWS, signals as sigs_short
from long_rules_backtest import precompute2, gen_signals
from long_robustness import portfolio, btc_regime
from long_search import COST, YEARS

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def precompute_extra(d):
    c = pd.Series(d["c"])
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    d["rsi_v"] = (100 - 100 / (1 + rs)).to_numpy()
    d["ema20_v"] = c.ewm(span=20, adjust=False).mean().to_numpy()


def make_exit(book, hold=96, tp=None, retrace=None, rsi_thr=None,
              sig_after=None, be_arm=None, chand=None, ema_state=False,
              climax=None):
    side = -1 if book == "short" else 1

    def exit_fn(d, i):
        t, h, l, c = d["t"], d["h"], d["l"], d["c"]
        n = len(t)
        entry = c[i]
        natr = d["natr_v"][i]
        natr = natr if natr == natr else 0.02
        if side < 0:
            level = h[i - 16:i + 1].max()
            sl_dist = abs(level / entry - 1)
        else:
            level = None
            sl_dist = max(2 * natr, 0.005)
        tp_level = None
        if tp is not None:
            tp_level = entry * (1 - tp) if side < 0 else entry * (1 + tp)
        if retrace is not None:                       # short only
            base = c[i - 16]
            tp_level = entry * (1 - retrace) + base * retrace
        best = entry
        armed = False
        end = min(i + hold, n - 1)

        def done(px, j, kind):
            return (side * (px / entry - 1) - COST, t[j] + M15, kind, sl_dist)

        for j in range(i + 1, end + 1):
            if level is not None and \
                    ((h[j] > level) if side < 0 else (l[j] < level)):
                return done(level, j, "sl")
            if tp_level is not None and \
                    ((l[j] <= tp_level) if side < 0 else (h[j] >= tp_level)):
                return done(tp_level, j, "tp")
            if chand is not None:
                if side < 0:
                    best = min(best, l[j])
                    lvl = best * (1 + chand * natr)
                    level = lvl if level is None else min(level, lvl)
                else:
                    best = max(best, h[j])
                    lvl = best * (1 - chand * natr)
                    level = lvl if level is None else max(level, lvl)
            if be_arm is not None:
                hitarm = (l[j] <= entry * (1 - be_arm)) if side < 0 \
                    else (h[j] >= entry * (1 + be_arm))
                if hitarm:
                    level = entry if level is None else \
                        (min(level, entry) if side < 0 else max(level, entry))
            prof = side * (c[j] / entry - 1)
            if rsi_thr is not None and d["rsi_v"][j] == d["rsi_v"][j]:
                if (d["rsi_v"][j] <= rsi_thr) if side < 0 \
                        else (d["rsi_v"][j] >= rsi_thr):
                    return done(c[j], j, "rsi")
            if sig_after is not None and prof >= sig_after:
                rev = (c[j] > c[j - 1]) if side < 0 else (c[j] < c[j - 1])
                if rev:
                    return done(c[j], j, "sig")
            if ema_state and side > 0:
                if not armed and c[j] > d["ema20_v"][j]:
                    armed = True
                elif armed and c[j] < d["ema20_v"][j]:
                    return done(c[j], j, "ema")
            if climax is not None and prof >= climax:
                volr = d["volr_v"][j]
                blow = (c[j] < c[j - 1]) if side < 0 else (c[j] > c[j - 1])
                if volr == volr and volr >= 3 and blow:
                    return done(c[j], j, "clmx")
        return done(c[end], end, "time")

    return exit_fn


def run_policy(label, rows_by_win, tickers, exit_fn, store):
    allt, rets, dds = [], [], []
    for name, a, b in WINDOWS:
        trades, eqh = portfolio(rows_by_win[name], tickers, exit_fn)
        met = metrics(eqh, ts(a), ts(b))
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        allt += trades
    g = pd.DataFrame(allt) if allt else pd.DataFrame(
        columns=["net", "t", "kind", "ticker"])
    comp = float(np.prod([1 + r for r in rets]) - 1)
    nt = g["net"].mean() * 100 if len(g) else 0
    md = g["net"].median() * 100 if len(g) else 0
    wr = (g["net"] > 0).mean() * 100 if len(g) else 0
    kinds = g["kind"].value_counts(normalize=True).to_dict() if len(g) else {}
    ks = " ".join(f"{k}:{v*100:.0f}%" for k, v in sorted(kinds.items()))
    posy = []
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        for y in YEARS:
            gy = g[g["year"] == y]
            posy.append(f"{y}:{gy['net'].mean()*100:+.2f}/{len(gy)}"
                        if len(gy) else f"{y}:--")
    p(f"{label:30s} {len(g):4d} {nt:+8.3f}% {md:+7.2f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:6.1f}%  {ks:24s} " + " | ".join(posy))
    store.append((label, nt, len(g), comp))
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute2(d)
        precompute_extra(d)
    p(f"EXIT LAB — {stamp} | {len(tickers)} tickers | full span 2023-01 -> "
      "2026-10 | entries FIXED, exits swept")
    hdr = (f"{'policy':30s} {'tr':>4s} {'net/tr':>8s} {'median':>7s} "
           f"{'win%':>4s} {'comp':>9s} {'dd':>6s}  {'exit mix':24s} by year")

    # ---- entry rows generated once per book, reused across policies
    srows, lrows = {}, {}
    bull = btc_regime(tickers)
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        srows[name] = sorted((tsg, tk, i) for tk, d in tickers.items()
                             for tsg, i in sigs_short(d, t0, t1))
        lrows[name] = sorted((tsg, tk, i) for tk, d in tickers.items()
                             for tsg, i in gen_signals(d, t0, t1, trig="r24",
                                                       depth=0.20)
                             if not bull(tsg))

    p("")
    p("=" * 132)
    p("SHORT BOOK — rule P entries, native 4h-high stop in every row")
    p(hdr)
    ss = []
    run_policy("time 4h (= deployed base)", srows, tickers,
               make_exit("short", hold=16), ss)
    run_policy("time 24h", srows, tickers, make_exit("short", hold=96), ss)
    for x in (0.05, 0.08, 0.12):
        run_policy(f"tp -{x:.0%} (24h cap)", srows, tickers,
                   make_exit("short", hold=96, tp=x), ss)
    for f in (0.5, 0.75, 1.0):
        run_policy(f"retrace {f:.0%} of pump", srows, tickers,
                   make_exit("short", hold=96, retrace=f), ss)
    run_policy("rsi <= 25", srows, tickers,
               make_exit("short", hold=96, rsi_thr=25), ss)
    run_policy("rsi <= 20", srows, tickers,
               make_exit("short", hold=96, rsi_thr=20), ss)
    run_policy("green close after +3%", srows, tickers,
               make_exit("short", hold=96, sig_after=0.03), ss)
    run_policy("green close after +6%", srows, tickers,
               make_exit("short", hold=96, sig_after=0.06), ss)
    run_policy("be-lock after +5%", srows, tickers,
               make_exit("short", hold=96, be_arm=0.05), ss)
    run_policy("chandelier 2*natr", srows, tickers,
               make_exit("short", hold=96, chand=2.0), ss)
    run_policy("vol-climax flush after +2%", srows, tickers,
               make_exit("short", hold=96, climax=0.02), ss)
    run_policy("tp -8% + be-lock +5%", srows, tickers,
               make_exit("short", hold=96, tp=0.08, be_arm=0.05), ss)

    p("")
    p("=" * 132)
    p("LONG BOOK — capit entries (-20%/24h fresh, BTC-bear-gated), no "
      "native stop")
    p(hdr)
    ls = []
    run_policy("time 24h (= deployed capit)", lrows, tickers,
               make_exit("long", hold=96), ls)
    run_policy("time 48h (= capit_slow)", lrows, tickers,
               make_exit("long", hold=192), ls)
    for x in (0.10, 0.20, 0.30):
        run_policy(f"tp +{x:.0%} (48h cap)", lrows, tickers,
                   make_exit("long", hold=192, tp=x), ls)
    run_policy("red close after +5%", lrows, tickers,
               make_exit("long", hold=192, sig_after=0.05), ls)
    run_policy("red close after +10%", lrows, tickers,
               make_exit("long", hold=192, sig_after=0.10), ls)
    run_policy("rsi >= 70", lrows, tickers,
               make_exit("long", hold=192, rsi_thr=70), ls)
    run_policy("rsi >= 80", lrows, tickers,
               make_exit("long", hold=192, rsi_thr=80), ls)
    run_policy("ema20 recross (armed)", lrows, tickers,
               make_exit("long", hold=192, ema_state=True), ls)
    run_policy("be-lock after +10%", lrows, tickers,
               make_exit("long", hold=192, be_arm=0.10), ls)
    run_policy("chandelier 3*natr", lrows, tickers,
               make_exit("long", hold=192, chand=3.0), ls)
    run_policy("vol-climax blowoff after +5%", lrows, tickers,
               make_exit("long", hold=192, climax=0.05), ls)
    run_policy("tp +20% + be-lock +10%", lrows, tickers,
               make_exit("long", hold=192, tp=0.20, be_arm=0.10), ls)

    for lab, store in (("SHORT", ss), ("LONG", ls)):
        p("")
        p(f"{lab} RANKED by net/trade:")
        for label, nt, ntr, comp in sorted(store, key=lambda x: -x[1]):
            p(f"  {label:32s} {nt:+8.3f}%/tr x {ntr:4d} | comp {comp*100:+9.2f}%")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/exit_lab_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
