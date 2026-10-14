#!/usr/bin/env python3
"""Is 'TP beats hold' sticky month to month, or a streak?

Monthly return difference (tp+5% minus hold24h) from the fleet sim,
then: sign-repeat rate vs coin flip, lag-1 autocorrelation, and the
hit rate of 'use last month's winner this month'.

Usage: PYTHONPATH=research python3 research/loser_exit_persistence.py
Writes: reports/loser_exit_persistence_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from regime_switch_backtest import load_full
from hourly_explore import precompute, build_panel
from loser_equity_curves import simulate

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

    hold = simulate(grid, tks, panel, tickers, {"kind": "time"}, hold=96)
    tp = simulate(grid, tks, panel, tickers, {"kind": "tp", "x": 0.05}, hold=96)

    m_hold = hold.resample("ME").last().pct_change().dropna()
    m_tp = tp.resample("ME").last().pct_change().dropna()
    diff = (m_tp - m_hold).dropna()

    p(f"LOSER EXIT PERSISTENCE — {stamp}")
    p(f"months: {len(diff)}  |  tp-minus-hold monthly mean "
      f"{diff.mean()*100:+.2f}%  median {diff.median()*100:+.2f}%")
    p("")
    sign = np.sign(diff.values)
    rep = (sign[1:] == sign[:-1]).mean()
    ac1 = diff.autocorr(1)
    p(f"sign repeat rate        {rep*100:.0f}%   (coin flip = 50%)")
    p(f"lag-1 autocorrelation   {ac1:+.2f}")
    # strategy: each month use whichever exit won last month
    pick_tp = sign[:-1] > 0
    sw = np.where(pick_tp, m_tp.values[1:], m_hold.values[1:])
    for lab, r in (("always hold", m_hold.values[1:]),
                   ("always tp5", m_tp.values[1:]),
                   ("follow last month", sw)):
        tot = np.prod(1 + r) - 1
        p(f"{lab:20s} total {tot*100:+9.1f}%  mean/mo {r.mean()*100:+.2f}%")
    p("")
    p("tp-minus-hold by month:")
    for ts, v in diff.items():
        p(f"  {ts:%Y-%m}  {v*100:+7.2f}%")
    os.makedirs("reports", exist_ok=True)
    out = (f"reports/loser_exit_persistence_"
           f"{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
