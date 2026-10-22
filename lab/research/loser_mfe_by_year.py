#!/usr/bin/env python3
"""Did the bounce die, or just the hold? Peak gain (MFE on closes,
within 24h) vs final 24h return, by year, baseline loser rule.

Usage: PYTHONPATH=research python3 research/loser_mfe_by_year.py
Writes: reports/loser_mfe_by_year_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST
from hourly_explore import precompute, build_panel, H_MS

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
    rows = []
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
        rr = c[i + 1:k + 1] / c[i] - 1
        peak = rr.max()
        tpk = (int(np.argmax(rr)) + 1) / 4          # hours to peak
        rows.append(dict(t=grid[r], peak=peak, tpk=tpk, final=rr[-1]))
    g = pd.DataFrame(rows)
    g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
    p(f"LOSER MFE BY YEAR — {stamp}")
    p("baseline rule, peak/final on closes within 24h, gross (cost "
      f"{COST*100:.2f}% not subtracted)")
    p("")
    p(f"{'year':<6}{'n':>7}{'peak mean':>10}{'peak med':>10}"
      f"{'>=+3%':>7}{'>=+5%':>7}{'t2pk med':>9}{'final mean':>11}"
      f"{'giveback':>9}")
    for y, gg in g.groupby("year"):
        gb = (gg["peak"] - gg["final"]).mean()
        p(f"{y:<6}{len(gg):>7,}{gg['peak'].mean()*100:>9.2f}%"
          f"{gg['peak'].median()*100:>9.2f}%"
          f"{(gg['peak']>=0.03).mean()*100:>6.0f}%"
          f"{(gg['peak']>=0.05).mean()*100:>6.0f}%"
          f"{gg['tpk'].median():>8.1f}h"
          f"{gg['final'].mean()*100:>10.2f}%"
          f"{gb*100:>8.2f}%")
    p("")
    # 2026 by month
    g26 = g[g["year"] == 2026].copy()
    g26["month"] = pd.to_datetime(g26["t"], unit="ms").dt.month
    p("2026 by month:")
    for m, gg in g26.groupby("month"):
        p(f"  2026-{m:02d} n {len(gg):4,}  peak med "
          f"{gg['peak'].median()*100:+.2f}%  >=+5% "
          f"{(gg['peak']>=0.05).mean()*100:3.0f}%  final "
          f"{gg['final'].mean()*100:+.2f}%")
    os.makedirs("reports", exist_ok=True)
    out = f"reports/loser_mfe_by_year_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt"
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
