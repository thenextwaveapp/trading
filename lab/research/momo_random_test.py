#!/usr/bin/env python3
"""MOMO LONG on random universes — the untested live book (ts30/momo30).

Signal (mirrors paper_fleet.signal_momo / indicator_tests.sigs_long_momo):
runup >= 12%/4h, vol >= 2.5x, synthetic-4h upper wick <= 15%, close in top
20% of range; stop max(4h low, body mid)-0.1%; 12h hold. Gate: pump dial
m > +2% (continuation regime). Flat 10%/1x sizing — this is a signal-level
universe test, not a sizing ladder.

Invo 60 vs 3 random draws of 60 crypto perps, 2025-26 window.

Usage: python3 research/momo_random_test.py
Writes: reports/momo_random_<stamp>.txt
"""
import random
from datetime import datetime, timezone

import numpy as np

from backtest import M15
from rules_backtest import load, alive
from degen_derby import COST, START
from regime_switch_backtest import pump_events, make_dial
from indicator_tests import anatomy
from random_degen_test import TRADFI
from super_larry_wide import load_wide_era

HOLD = 48          # 12h in 15m bars
FRAC = 0.10
N, SEEDS = 60, (1, 2, 3)

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def sig_momo(tickers):
    rows = []
    for tk, d in tickers.items():
        t, c, v = d["t"], d["c"], d["v"]
        for i in range(20, len(t) - 1):
            if not alive(d, i):
                continue
            if c[i] / c[i - 16] - 1 < 0.12:
                continue
            mu = v[i - 8:i].mean()
            if mu <= 0 or v[i] / mu < 2.5:
                continue
            a = anatomy(d, i)
            if a is None or a["upwick"] > 0.15 or a["closeloc"] < 0.80:
                continue
            stop = max(a["L"], (a["O"] + a["C"]) / 2) * 0.999
            rows.append((t[i] + M15, tk, i, stop))
    rows.sort()
    return rows


def run(tickers, dial):
    rows = sig_momo(tickers)
    eq, peak, maxdd = START, START, 0.0
    open_until = {}
    nets = []
    for t_sig, tk, i, stop in rows:
        if open_until.get(tk, 0) > t_sig:
            continue
        s, n, m = dial(t_sig)
        if m != m or m <= 0.02:          # continuation gate: dial > +2%
            continue
        d = tickers[tk]
        t, l, c = d["t"], d["l"], d["c"]
        entry = c[i]
        end = min(i + HOLD, len(t) - 1)
        net, exit_j = None, end
        for j in range(i + 1, end + 1):
            if l[j] <= stop:
                net, exit_j = stop / entry - 1 - COST, j
                break
        if net is None:
            net = c[end] / entry - 1 - COST
        nets.append(net)
        eq += eq * FRAC * net
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
        open_until[tk] = t[exit_j]
    nets = np.array(nets)
    return eq, maxdd, len(nets), (nets.mean() if len(nets) else float("nan")), \
        ((nets > 0).mean() if len(nets) else float("nan"))


def report(tag, tickers):
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)
    eq, maxdd, n, avg, win = run(tickers, dial)
    p(f"  {tag:42s} trades {n:4d}  avg {avg*100:+6.2f}%  win "
      f"{win*100:4.0f}%  $10k -> ${eq:>9,.0f}  dd {maxdd*100:6.1f}%")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"MOMO LONG RANDOM-UNIVERSE TEST — {stamp}")
    p(f"gate dial>+2% | 12h hold | stop 4h-low/body-mid | flat {FRAC:.0%}/1x")
    p("")

    curated, _ = load("backtest/r60_candles_15m.csv.gz",
                      "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))
    report("INVO 60 (control)", curated)

    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    pool = sorted(tk for tk in wide if tk not in TRADFI)
    for seed in SEEDS:
        draw = random.Random(seed).sample(pool, N)
        report(f"RANDOM DEGEN 60 — draw {seed}",
               {tk: wide[tk] for tk in draw})

    fname = ("reports/momo_random_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
