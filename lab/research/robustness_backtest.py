#!/usr/bin/env python3
"""Robustness checks for the base pump-short on the existing 2025-26 data.
No new parameters are being selected here — these probe the base rule as-is.

  A. W0: untouched 2024-12-15 -> 2025-03-01 sliver (pre-W1), portfolio run
  B. Entry-delay ladder: enter 0/1/2/4 candles after the signal (per-trade)
  C. Cost stress: base trades at 1x/2x/4x fee+slip
  D. Random-short control: same tickers, random times, same exit mechanics
  E. Bootstrap CI on net/trade + signal clustering by day

Usage: python3 robustness_backtest.py
Writes: reports/robustness_backtest_<stamp>.txt
"""
import os
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from rules_backtest import load, alive, TAKER, SLIP
from variants_backtest import signals_v
from holds_stops_backtest import portfolio

COST = 2 * TAKER + SLIP

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def trade_net(d, i, delay=0, cost=COST):
    """Short at close[i+delay], stop = signal-time 4h high, hold 16 from entry.
    Returns net or None (not enough candles / entry already above stop)."""
    j0 = i + delay
    if j0 + 17 >= len(d["t"]):
        return None
    entry = d["c"][j0]
    sl_level = d["h"][i - 16:i + 1].max()
    if entry >= sl_level:
        return None
    for j in range(j0 + 1, j0 + 17):
        if d["h"][j] > sl_level:
            return -(sl_level / entry - 1) - cost
    return -(d["c"][j0 + 16] / entry - 1) - cost


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    p(f"ROBUSTNESS CHECKS (base rule) — {stamp}")

    t_lo, t_hi = ts("2024-12-16"), ts("2026-10-04")
    sigs = []
    for tk, d in tickers.items():
        sigs += [(tsg, tk, i, ru) for tsg, i, ru in signals_v(d, t_lo, t_hi, 0.12, 2.0)]
    sigs.sort()
    p(f"signals, full span: {len(sigs)}")

    p("")
    p("A. W0 window 2024-12-16 -> 2025-03-01 (never used by any prior run)")
    w0 = [s for s in sigs if s[0] < ts("2025-03-01")]
    trades, eqh = portfolio(w0, tickers, dict(hold=16, stop="hh", buf=0.0))
    met = metrics(eqh, ts("2024-12-16"), ts("2025-03-01"))
    nets = [x["net"] for x in trades]
    if nets:
        p(f"   trades {len(trades)} | net/trade {np.mean(nets)*100:+.3f}% | "
          f"win {np.mean([n > 0 for n in nets])*100:.0f}% | eq {met['ret']*100:+.2f}% "
          f"dd {met['maxdd']*100:.2f}%")
    else:
        p("   no trades in window")

    p("")
    p("B. Entry-delay ladder (all signals, per-trade, no portfolio layer)")
    for delay in (0, 1, 2, 4):
        nets = [n for _, tk, i, _ in sigs
                if (n := trade_net(tickers[tk], i, delay)) is not None]
        p(f"   delay {delay:2d} candles ({delay*15:3d}m): n {len(nets):3d} | "
          f"net/trade {np.mean(nets)*100:+.3f}% | win {np.mean([n > 0 for n in nets])*100:.0f}%")

    p("")
    p("C. Cost stress (delay 0, per-trade)")
    base_nets = np.array([n for _, tk, i, _ in sigs
                          if (n := trade_net(tickers[tk], i, 0)) is not None])
    for mult in (1, 2, 4):
        stressed = base_nets - (mult - 1) * COST
        p(f"   {mult}x fees+slip ({mult*COST*100:.2f}%/trade): "
          f"net/trade {stressed.mean()*100:+.3f}%")

    p("")
    p("D. Random-short control — same tickers, random alive candles, same exits")
    rng = np.random.default_rng(7)
    fired = sorted({tk for _, tk, _, _ in sigs})
    ctrl = []
    for tk in fired:
        d = tickers[tk]
        lo = np.searchsorted(d["t"], t_lo)
        hi = np.searchsorted(d["t"], t_hi) - 20
        n_real = sum(1 for s in sigs if s[1] == tk)
        made = 0
        while made < n_real * 30:
            i = int(rng.integers(max(lo, 20), hi))
            if not alive(d, i):
                continue
            n = trade_net(d, i, 0)
            if n is not None:
                ctrl.append(n)
                made += 1
    p(f"   control shorts: n {len(ctrl)} | net/trade {np.mean(ctrl)*100:+.3f}% | "
      f"win {np.mean([n > 0 for n in ctrl])*100:.0f}%")
    p(f"   vs base signal shorts:        net/trade {base_nets.mean()*100:+.3f}% "
      f"-> condition edge {100*(base_nets.mean()-np.mean(ctrl)):+.3f}%/trade")

    p("")
    p("E. Bootstrap & clustering (delay-0 per-trade nets)")
    boots = [rng.choice(base_nets, len(base_nets), replace=True).mean()
             for _ in range(10_000)]
    lo5, hi95 = np.percentile(boots, [5, 95])
    p(f"   mean {base_nets.mean()*100:+.3f}% | 90% CI [{lo5*100:+.3f}%, {hi95*100:+.3f}%] "
      f"| P(mean<=0) {np.mean(np.array(boots) <= 0)*100:.1f}%")
    days = Counter(datetime.fromtimestamp(s[0] / 1000, timezone.utc).date()
                   for s in sigs)
    p(f"   {len(sigs)} signals across {len(days)} distinct days | "
      f"max signals in one day: {max(days.values())}")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/robustness_backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
