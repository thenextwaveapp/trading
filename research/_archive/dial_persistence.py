#!/usr/bin/env python3
"""DIAL PERSISTENCE — full-greed shorts only after the dial has held
negative for P consecutive days. Tests P in {0, 15, 30, 60, 90} on all
three eras, S leg at the tuned sizing (25%x(runup/12%)^2 cap50, 3x).

The era20 finding: gate flickers (brief dial dips in a buying regime) let
full-size shorts through and killed the book. Real short regimes hold
negative for months. Persistence should filter flickers, keep regimes.

Usage: python3 dial_persistence.py
Writes: reports/dial_persistence_<stamp>.txt
"""
from datetime import datetime, timezone

from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
from regime import persistent_dial
import super_larry as SL

DAY = 86_400_000
CFG = dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30))

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"DIAL PERSISTENCE — {stamp} | S leg, tuned sizing, gate requires dial<0 "
      f"held P consecutive days")
    p("")
    tracks = []
    for label, c15, c1 in [
        ("2020-22 era20 (166tk)", "backtest/era20_15m.csv.gz", "backtest/era20_1h.csv.gz"),
        ("2023-24 bear (45tk)", "backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main (60tk)", "backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz"),
    ]:
        tickers, regime_at = load(c15, c1)
        for d in tickers.values():
            precompute(d)
        ev = pump_events(tickers)
        dial = make_dial(*ev, 30, 0.0)
        t0 = min(d["t"][0] for d in tickers.values())
        t1 = max(d["t"][-1] for d in tickers.values())
        tracks.append((label, tickers, regime_at, dial, t0, t1))
        p(f"loaded {label}: {len(tickers)} tickers, {len(ev[0]):,} events")
    p("")

    chain = {}
    p(f"{'P (days)':>9s}" + "".join(f"  {lab.split(' (')[0]:>22s}" for lab, *_ in tracks)
      + f"  {'chained $10k':>14s}")
    for P in (0, 15, 30, 60, 90):
        cells, mult = [], 1.0
        for label, tickers, regime_at, dial, t0, t1 in tracks:
            dp = dial if P == 0 else persistent_dial(dial, t0, t1, P)
            eq, maxdd, n_s, n_c, sk, lq = SL.run_book(
                tickers, dp, regime_at, CFG, legs=("S",))
            mult *= eq / START
            cells.append(f"${eq:>9,.0f} {maxdd*100:5.0f}%")
        p(f"{P:>9d}" + "".join(f"  {c:>22s}" for c in cells)
          + f"  ${START*mult:>13,.0f}")

    fname = f"reports/dial_persistence_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
