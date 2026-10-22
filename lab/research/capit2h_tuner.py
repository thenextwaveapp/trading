#!/usr/bin/env python3
"""CAPIT_2H TUNER — grid-search the 2h-cascade long for its most
profitable expression, then check the winners transfer.

Signal: 2h return <= -depth, fresh crossing, 24h per-ticker cooldown,
long at event close (knife — the event study showed waiting costs),
no stop, hold H, sized like the fleet's capit (risk on 2xNATR24).

Grid (Invo 60, 2025-26): depth x hold x gate -> 32 cells.
Transfer check for the top-3 gated cells: 2023-24 track and the
liquid-outsider 60 (universe robustness).

Usage: python3 research/capit2h_tuner.py
Writes: reports/capit2h_tuner_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from backtest import M15
from rules_backtest import load, natr_at
from degen_derby import precompute, START
from fleet_race import race
from super_larry_wide import load_wide_era
from random_degen_test import TRADFI

DEPTHS = (0.06, 0.08, 0.10, 0.12)
HOLDS = [("6h", 24), ("24h", 96), ("48h", 192), ("72h", 288)]
DAY = 86_400_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def cascade_rows(tickers, depth, hold, regime_at, gated):
    rows = []
    for tk, d in tickers.items():
        t, c, v, h, l = (d[k] for k in "tcvhl")
        last = -10**18
        for i in range(9, len(t) - 1):
            if t[i] - last < DAY:
                continue
            if t[i] - t[i - 8] != 8 * M15:
                continue
            if (v[i - 8:i + 1] <= 0).any() or h[i] == l[i]:
                continue
            if c[i] / c[i - 8] - 1 > -depth:
                continue
            r2p = c[i - 1] / c[i - 9] - 1 if t[i - 1] - t[i - 9] == 8 * M15 \
                else 0.0
            if r2p <= -depth:
                continue
            last = t[i]
            t_sig = t[i] + M15
            if gated and regime_at(t_sig) is not False:
                continue
            na = natr_at(d, t_sig)
            rows.append((t_sig, tk, dict(
                i=i, side=1, entry=c[i], stop=None, hold=hold,
                trail_k=None, natr=None, sizing="risk",
                sl_dist=max(2 * (na if na is not None else 0), 0.005))))
    rows.sort(key=lambda r: r[0])
    return rows


def cell(tickers, regime_at, depth, hold, gated):
    rows = cascade_rows(tickers, depth, hold, regime_at, gated)
    return race(tickers, rows, dict(stop=("none", 0)))


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"CAPIT_2H TUNER — {stamp} | knife entry, no stop, capit sizing")
    p("")
    curated, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))
    for d in curated.values():
        precompute(d)

    p("GRID — Invo 60, 2025-26")
    p(f"  {'cell':24s} {'$10k ->':>11s} {'ret%':>7s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg':>7s}")
    results = []
    for gated in (True, False):
        for depth in DEPTHS:
            for hlab, hold in HOLDS:
                eq, maxdd, n, avg, win = cell(curated, regime_at, depth,
                                              hold, gated)
                tag = f"-{depth*100:.0f}%/2h {hlab} {'bear' if gated else 'ung'}"
                results.append((tag, depth, hold, gated, eq, maxdd))
                p(f"  {tag:24s} ${eq:>10,.0f} {(eq/START-1)*100:+6.1f}% "
                  f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+6.2f}%")
    p("")

    top = sorted([r for r in results if r[3]], key=lambda r: -r[4])[:3]
    p("TRANSFER — top-3 gated cells on 2023-24 and the outsider 60")
    old, regime_old = load("backtest/r60_oos_15m.csv.gz",
                           "backtest/r60_oos_1h.csv.gz")
    for d in old.values():
        precompute(d)
    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    wide = {tk: d for tk, d in wide.items() if tk not in TRADFI}
    dv = {tk: float(np.median(d["c"] * d["v"])) for tk, d in wide.items()}
    out60 = {tk: wide[tk] for tk in
             sorted(dv, key=dv.get, reverse=True)[:60]}
    for d in out60.values():
        precompute(d)
    p(f"  {'cell':24s} {'2023-24':>22s} {'outsider60 25-26':>22s}")
    for tag, depth, hold, gated, eq, maxdd in top:
        e1, m1, n1, a1, w1 = cell(old, regime_old, depth, hold, True)
        e2, m2, n2, a2, w2 = cell(out60, regime_at, depth, hold, True)
        p(f"  {tag:24s} ${e1:>9,.0f} {m1*100:5.1f}% n={n1:<4d} "
          f"${e2:>9,.0f} {m2*100:5.1f}% n={n2:<4d}")

    fname = ("reports/capit2h_tuner_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
