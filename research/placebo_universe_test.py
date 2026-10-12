#!/usr/bin/env python3
"""PLACEBO UNIVERSE — same strategy, same period, different 60 coins.

Take the 2025-26 main track and swap the universe: instead of the Invo
traders' 60, use the NEXT 60 most liquid Binance perps (by median 15m
dollar volume over the window, from the wide cache, excluding the 60).
Same ladder, same dial machinery, same window. If the strategy performs
on the placebo 60 too, the Invo selection isn't special — it's just
liquid degen coins. If it dies, the selection is the edge.

Usage: python3 research/placebo_universe_test.py
Writes: reports/placebo_universe_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL
from super_larry_wide import load_wide_era, LADDER

WDAYS, THR = 30, 0.0

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def run_ladder(tag, tickers, dial, regime_at):
    p(f"  [{tag}] {len(tickers)} tickers")
    p(f"  {'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>5s} {'C':>5s} "
      f"{'skip':>6s} {'liq':>4s}")
    for name, cfg in LADDER:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at, cfg)
        p(f"  {name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")
    cfg = LADDER[3][1]
    for legs, nm in [(("S",), "  -> leg S alone (Larry sizing)"),
                     (("C",), "  -> leg C alone (Larry sizing)")]:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at,
                                                  cfg, legs=legs)
        p(f"  {nm:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"PLACEBO UNIVERSE TEST — {stamp}")
    p("2025-26 main window | placebo = next 60 most liquid perps by median "
      "15m dollar volume (wide cache, Invo-60 excluded)")
    p("")

    curated, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))

    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    dv = {tk: float(np.median(d["c"] * d["v"])) for tk, d in wide.items()}
    placebo_tks = sorted(dv, key=dv.get, reverse=True)[:60]
    placebo = {tk: wide[tk] for tk in placebo_tks}
    p("placebo 60 (median 15m $vol, $k):")
    for i in range(0, 60, 6):
        p("  " + "  ".join(f"{tk}({dv[tk]/1e3:,.0f})"
                           for tk in placebo_tks[i:i + 6]))
    p("")

    for tag, uni in [("INVO 60 (the real universe)", curated),
                     ("PLACEBO 60 (next-most-liquid, no Invo)", placebo)]:
        for d in uni.values():
            precompute(d)
        ev = pump_events(uni)
        dial = make_dial(*ev, WDAYS, THR)
        p(f"  pump events: {len(ev[0]):,}")
        run_ladder(tag, uni, dial, regime_at)
        p("")

    fname = ("reports/placebo_universe_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
