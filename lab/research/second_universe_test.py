#!/usr/bin/env python3
"""SECOND UNIVERSE TEST — does the capit edge survive as a PORTFOLIO on
the 60 most liquid crypto perps OUTSIDE the Invo 60? (The universe_map
said their per-coin capit expectancy matches the 60; the old placebo was
half TradFi. This is the clean test.) 2025-26 window, fleet sizing.

Arms per universe: capit (24h hold, bear-gated), capit_slow (48h), and
capit_ng (ungated) — the three strongest fleet capit shapes.

Usage: python3 research/second_universe_test.py
Writes: reports/second_universe_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, START
from fleet_race import sig_capit_rows, race
from super_larry_wide import load_wide_era
from random_degen_test import TRADFI

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


ARMS = [
    ("capit (24h, bear-gated)", dict(depth=0.20, hold=96, btc_bear=True,
                                     stop=("none", 0))),
    ("capit_slow (48h, bear-gated)", dict(depth=0.20, hold=192,
                                          btc_bear=True, stop=("none", 0))),
    ("capit_ng (24h, ungated)", dict(depth=0.20, hold=96, btc_bear=False,
                                     stop=("none", 0))),
]


def run_uni(tag, uni, regime_at):
    p(f"  [{tag}] {len(uni)} tickers")
    p(f"  {'arm':30s} {'$10k ->':>11s} {'ret%':>7s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg':>7s}")
    for name, cfg in ARMS:
        rows = sig_capit_rows(uni, cfg, regime_at)
        eq, maxdd, n, avg, win = race(uni, rows, cfg)
        p(f"  {name:30s} ${eq:>10,.0f} {(eq/START-1)*100:+6.1f}% "
          f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+6.2f}%")
    p("")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"SECOND UNIVERSE TEST — {stamp} | 2025-26 | fleet sizing")
    p("outsider 60 = most liquid crypto perps NOT in the Invo 60 "
      "(TradFi excluded) — liquidity-selected, performance-blind")
    p("")
    curated, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))
    for d in curated.values():
        precompute(d)
    run_uni("INVO 60 (control)", curated, regime_at)

    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    wide = {tk: d for tk, d in wide.items() if tk not in TRADFI}
    dv = {tk: float(np.median(d["c"] * d["v"])) for tk, d in wide.items()}
    out60_tks = sorted(dv, key=dv.get, reverse=True)[:60]
    out60 = {tk: wide[tk] for tk in out60_tks}
    for d in out60.values():
        precompute(d)
    p("outsider 60: " + " ".join(sorted(out60_tks)))
    p("")
    run_uni("OUTSIDER 60 (liquid crypto, no Invo)", out60, regime_at)

    fname = ("reports/second_universe_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
