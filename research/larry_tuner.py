#!/usr/bin/env python3
"""LARRY TUNER — fine-tune the whole rig on the main track.

Grid: hold (4h/8h/24h) x leverage (3..6) x sizing curve:
frac = base * (runup/12%)^power, capped. Same 163 base-rule signals,
same 4h-high stop, max 4 concurrent, compounding, liquidations on.

Usage: python3 larry_tuner.py
Writes: reports/larry_tuner_<stamp>.txt, backtest/larry_tuner_grid.csv
"""
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd

from rules_backtest import load
from degen_derby import precompute, sig_pump, resolve, START
from backtest import M15

CONC = 4

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    sigs = []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        sigs += [(d["t"][i] + M15, tk, i) for i in ii]
    sigs.sort()

    HOLDS = [(16, "4h"), (32, "8h"), (96, "24h")]
    LEVS = [3, 4, 5, 6]
    BASES = [0.15, 0.25, 0.35]
    POWERS = [0.0, 0.5, 1.0, 1.5, 2.0]
    CAPS = [0.50, 0.75]

    # pre-resolve every signal once per (hold, lev)
    resolved = {}
    for (hold, _), lev in product(HOLDS, LEVS):
        key = (hold, lev)
        resolved[key] = {}
        for t_sig, tk, i in sigs:
            resolved[key][(tk, i)] = resolve(tickers[tk], i, "short", hold, "4hhigh", lev)

    def run(hold, lev, base, power, cap):
        R = resolved[(hold, lev)]
        eq, peak, maxdd = START, START, 0.0
        pending, open_until = [], {}
        trades = liqs = 0
        for t_sig, tk, i in sigs:
            pending.sort()
            while pending and pending[0][0] <= t_sig:
                et, pnl, lq = pending.pop(0)
                eq += pnl
                liqs += lq
                peak = max(peak, eq)
                maxdd = min(maxdd, eq / peak - 1)
            if eq < START * 0.01:
                return 0.0, maxdd, trades, liqs, True
            if open_until.get(tk, 0) > t_sig:
                continue
            if sum(1 for x in open_until.values() if x > t_sig) >= CONC:
                continue
            net, exit_t, kind = R[(tk, i)]
            ru = tickers[tk]["runup_v"][i]
            frac = min(base * (ru / 0.12) ** power, cap)
            margin = min(frac * eq, eq)
            pnl = max(margin * lev * net, -margin)
            pending.append((exit_t, pnl, kind == "LIQUIDATED"))
            open_until[tk] = exit_t
            trades += 1
        for et, pnl, lq in sorted(pending):
            eq += pnl
            liqs += lq
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        return max(eq, 0.0), maxdd, trades, liqs, False

    rows = []
    for (hold, hname), lev, base, power, cap in product(HOLDS, LEVS, BASES, POWERS, CAPS):
        eq, maxdd, trades, liqs, busted = run(hold, lev, base, power, cap)
        rows.append(dict(hold=hname, lev=lev, base=base, power=power, cap=cap,
                         final=eq, maxdd=maxdd, trades=trades, liqs=liqs, busted=busted,
                         calm=eq / START / max(-maxdd, 0.01)))
    g = pd.DataFrame(rows).sort_values("final", ascending=False)
    g.to_csv("backtest/larry_tuner_grid.csv", index=False)

    p(f"LARRY TUNER — {stamp} | {len(g)} configs | same 163 signals, stop=4h-high, conc {CONC}")
    p(f"frac = base x (runup/12%)^power, capped | busted: {int(g.busted.sum())} configs")
    p("")
    p("TOP 20 BY FINAL EQUITY:")
    p(f"  {'hold':>4s} {'lev':>3s} {'base':>5s} {'pow':>4s} {'cap':>4s} {'final':>14s} {'maxdd':>7s} {'liqs':>4s}")
    for _, r in g.head(20).iterrows():
        p(f"  {r.hold:>4s} {int(r.lev)}x  {r.base:5.2f} {r.power:4.1f} {r.cap:4.2f} "
          f"${r.final:>13,.0f} {r.maxdd*100:6.1f}% {int(r.liqs):4d}")
    p("")
    nb = g[~g.busted]
    p("TOP 10 'SLEEP AT NIGHT' (best final among maxdd better than -40%):")
    sane = nb[nb.maxdd > -0.40].sort_values("final", ascending=False)
    for _, r in sane.head(10).iterrows():
        p(f"  {r.hold:>4s} {int(r.lev)}x  {r.base:5.2f} {r.power:4.1f} {r.cap:4.2f} "
          f"${r.final:>13,.0f} {r.maxdd*100:6.1f}% {int(r.liqs):4d}")
    p("")
    p("MARGINALS (avg final across the rest of the grid, unbusted only):")
    for col in ["hold", "lev", "base", "power", "cap"]:
        parts = [f"{k}: ${v:,.0f}" for k, v in nb.groupby(col)["final"].mean().items()]
        p(f"  {col:6s} " + " | ".join(parts))

    fname = f"reports/larry_tuner_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
