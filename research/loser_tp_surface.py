#!/usr/bin/env python3
"""Optimal TP level x fallback hold for the loser engine.

Policy: exit at first close >= +x; if never, time exit at H bars.
Grid over x and H, expected net per trade by year, plus what the
no-TP remainder looks like (to sanity-check the fallback choice).

Usage: PYTHONPATH=research python3 research/loser_tp_surface.py
Writes: reports/loser_tp_surface_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST, YEARS
from hourly_explore import precompute, build_panel

TPS = (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10)
HOLDS = (24, 48, 96)                     # 6h / 12h / 24h fallback

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    paths, ts = [], []
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmin(row))
        if row[j] > -0.02:
            continue
        d = tickers[tks[j]]
        i = panel["idx"][r, j]
        t, c = d["t"], d["c"]
        k = i + 96
        if k >= len(t) or t[k] - t[i] != 96 * M15:
            continue
        paths.append(c[i + 1:k + 1] / c[i] - 1)
        ts.append(grid[r])
    R = np.vstack(paths)                       # [trade, bar]
    year = pd.to_datetime(pd.Series(ts), unit="ms").dt.year.to_numpy()
    p(f"LOSER TP SURFACE — {stamp}")
    p(f"{len(R):,} trades, net of {COST*100:.2f}% cost | "
      "exit first close >= +x else time H")
    p("")

    def policy_net(x, H):
        hit = R[:, :H] >= x
        has = hit.any(axis=1)
        first = np.argmax(hit, axis=1)
        out = np.where(has, R[np.arange(len(R)), first], R[:, H - 1])
        return out - COST, has

    p(f"{'':10s}" + "".join(f"{f'H={h//4}h':>12s}" for h in HOLDS)
      + "   (mean net %/trade, all years)")
    for x in TPS:
        row = []
        for H in HOLDS:
            net, _ = policy_net(x, H)
            row.append(f"{net.mean()*100:+11.3f}")
        p(f"tp {x*100:3.0f}%   " + " ".join(row))
    p(f"{'hold':8s}  " + " ".join(
        f"{(R[:, H-1] - COST).mean()*100:+11.3f}" for H in HOLDS))
    p("")

    p("by year (fallback H=24h):")
    hdr = f"{'tp':>6s}" + "".join(f"{y:>10d}" for y in YEARS) + f"{'hit%':>8s}"
    p(hdr)
    for x in TPS:
        net, has = policy_net(x, 96)
        cells = "".join(f"{net[year==y].mean()*100:>+9.3f}%" for y in YEARS)
        p(f"{x*100:5.0f}% {cells}{has.mean()*100:>7.0f}%")
    net_hold = R[:, 95] - COST
    p(f" hold " + "".join(f"{net_hold[year==y].mean()*100:>+9.3f}%"
                          for y in YEARS))
    p("")

    p("the no-TP remainder (fallback leg), tp=5%:")
    _, has5 = policy_net(0.05, 96)
    rem = ~has5
    for H in HOLDS:
        v = R[rem, H - 1] - COST
        p(f"  exit {H//4:2d}h: mean {v.mean()*100:+.3f}%  "
          f"med {np.median(v)*100:+.3f}%  win {(v>0).mean()*100:.0f}%")
    p("")

    os.makedirs("reports", exist_ok=True)
    out = f"reports/loser_tp_surface_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt"
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
