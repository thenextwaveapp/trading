#!/usr/bin/env python3
"""ERA20 TEST — Super Larry vs 2020-2022 (COVID crash, 2021 pump mania,
2022 LUNA/FTX bear). 166 tickers incl. delisted. The mania year is the
regime built to kill pump-shorts; the gate has never been tested on it.

Usage: python3 era20_test.py
Writes: reports/era20_test_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"ERA20 TEST — {stamp} | track: 2020-01 .. 2022-12, all perps with data")
    tickers, regime_at = load("backtest/era20_15m.csv.gz", "backtest/era20_1h.csv.gz")
    p(f"loaded {len(tickers)} tickers")
    for d in tickers.values():
        precompute(d)
    ev_t, ev_r, ev_done = pump_events(tickers)
    dial = make_dial(ev_t, ev_r, ev_done, 30, 0.0)
    p(f"pump events: {len(ev_t):,}")
    p("")

    p("DIAL BY MONTH (mean 24h fwd return of pump events, trailing 30d):")
    cur = datetime(2020, 2, 1, tzinfo=timezone.utc)
    while cur <= datetime(2022, 12, 1, tzinfo=timezone.utc):
        T = int(cur.timestamp() * 1000)
        s, n, m = dial(T)
        state = {-1: "SHORT", 0: "flat ", 1: "LONG "}[s]
        bar = ""
        if m == m and m is not None:
            k = int(abs(m) * 400)
            bar = ("+" if m > 0 else "-") * min(k, 40)
        p(f"  {cur.strftime('%Y-%m')}  {state}  n={n:4d}  "
          f"m={'n/a' if m != m or m is None else f'{m*100:+.2f}%'}  {bar}")
        cur = (cur.replace(day=28) + __import__('datetime').timedelta(days=5)).replace(day=1)
    p("")

    p(f"{'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>5s} {'C':>5s} {'skip':>6s}")
    for name, cfg, legs in [
        ("SUPER LARRY final spec (gated both legs)",
         dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30)), ("S", "C")),
        ("  S leg alone, GATED (gate30)",
         dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30)), ("S",)),
        ("  C leg alone (btc-bear gated)",
         dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30)), ("C",)),
        ("  Monk-size both legs (4%/1x)",
         dict(S=(0.04, 1, 0.0, 0.08), C=(0.04, 1, 0.0, 0.08)), ("S", "C")),
    ]:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at, cfg, legs=legs)
        p(f"{name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} {sk:6d}")

    # ungated S leg = what 2021 does to an ungated pump-shorter
    def dial_always_short(T):
        return -1, 999, -0.01
    eq, maxdd, n_s, n_c, sk, lq = SL.run_book(
        tickers, dial_always_short, regime_at,
        dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30)), legs=("S",))
    p(f"{'  S leg alone, UNGATED (the control group)':52s} ${eq:>12,.0f} "
      f"{maxdd*100:6.1f}% {n_s:5d} {n_c:5d} {sk:6d}")

    fname = f"reports/era20_test_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
