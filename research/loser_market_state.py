#!/usr/bin/env python3
"""Loser base rule bucketed by market state at entry.

Same trades as loser_variants_backtest baseline (thr 2%, hold 24h, re-entry
allowed, time exit). Each entry is tagged with BTC r24 and universe breadth
(share of alive tickers with negative r24) at the entry hour, then expectancy
is reported per bucket and bucket x year. No new rule — a conditioning cut.
"""
import sys
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(1, os.path.join(_here, "_archive"))   # archived deps still import
from regime_switch_backtest import load_full                    # noqa: E402
from long_search import YEARS                                   # noqa: E402
from hourly_explore import precompute, build_panel              # noqa: E402
from loser_variants_backtest import collect, OUT, p             # noqa: E402

E0 = {"kind": "time"}


def bucket_report(g, col, edges, labels):
    p(f"\n{col} at entry (base rule, net of costs)")
    g = g.dropna(subset=[col])
    g["b"] = pd.cut(g[col], edges, labels=labels)
    for lab in labels:
        s = g[g["b"] == lab]
        if not len(s):
            p(f"  {lab:18s} no trades")
            continue
        posy = " | ".join(
            f"{y}: {s[s['year']==y]['net'].mean()*100:+.3f}%/{len(s[s['year']==y])}"
            if len(s[s["year"] == y]) else f"{y}: --" for y in YEARS)
        p(f"  {lab:18s} {len(s):6,}  {s['net'].mean()*100:+7.3f}% "
          f"med {s['net'].median()*100:+6.3f}% win {(s['net']>0).mean()*100:3.0f}%")
        p(f"  {'':18s} {posy}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    p(f"LOSER x MARKET STATE — {stamp}")

    g = collect(grid, tks, panel, tickers, E0, thr=0.02, hold=96)
    p(f"base trades: {len(g):,}")

    # market state per grid row
    r24 = np.where(panel["alive"], panel["r24"], np.nan)
    with np.errstate(invalid="ignore"):
        breadth = np.nanmean(r24 < 0, axis=1)        # share of universe down 24h
        med24 = np.nanmedian(r24, axis=1)            # median universe r24
    btc = tickers.get("BTC")
    btc_r24 = {}
    if btc is not None:
        bt, bv = btc["t"], btc["r24_v"]
        idx = np.searchsorted(bt, grid, side="right") - 1
        ok = idx >= 0
        for r in np.where(ok)[0]:
            btc_r24[grid[r]] = bv[idx[r]]

    row_of = {int(t): r for r, t in enumerate(grid)}
    g["row"] = g["t"].map(row_of)
    g["breadth"] = g["row"].map(lambda r: breadth[r])
    g["med24"] = g["row"].map(lambda r: med24[r])
    g["btc24"] = g["t"].map(btc_r24)

    bucket_report(g, "btc24",
                  [-1, -0.05, -0.02, 0, 0.02, 0.05, 10],
                  ["<= -5%", "-5..-2%", "-2..0%", "0..+2%", "+2..+5%", "> +5%"])
    bucket_report(g, "breadth",
                  [-0.01, 0.25, 0.5, 0.75, 0.9, 1.01],
                  ["<25% down", "25-50%", "50-75%", "75-90%", ">90% down"])
    bucket_report(g, "med24",
                  [-1, -0.05, -0.02, 0, 0.02, 10],
                  ["<= -5%", "-5..-2%", "-2..0%", "0..+2%", "> +2%"])

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "reports",
                       f"loser_market_state_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    open(out, "w").write("\n".join(OUT) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
