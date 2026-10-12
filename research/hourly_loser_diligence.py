#!/usr/bin/env python3
"""Diligence on the hourly candidate: LONG the biggest 1h loser (>= move
threshold) every hour, time exit after H bars.

From hourly_explore.py: thr 2% / hold 24h -> +0.694%/trade net, 253/mo,
positive all 4 years, beats census 24h beta every year. But median is
negative (tail-carried) — so: concentration, re-entry policy, neighborhood,
cost stress, winners-dropped, per-ticker spread.

Usage: python3 hourly_loser_diligence.py
Writes: reports/hourly_loser_diligence_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST, YEARS
from hourly_explore import precompute, build_panel, fwd_net, H_MS

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def collect(grid, tks, panel, tickers, thr=0.02, hold=96, cost=COST,
            block_reentry=False):
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    open_until = {}
    rows = []
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmin(row))
        if row[j] > -thr:
            continue
        tk = tks[j]
        T = grid[r]
        if block_reentry and open_until.get(tk, 0) > T:
            continue
        d = tickers[tk]
        i = panel["idx"][r, j]
        net = fwd_net(d, i, hold, 1, cost)
        if net is None:
            continue
        open_until[tk] = T + hold * M15 // 1
        rows.append(dict(t=T, tk=tk, net=net, move=row[j]))
    g = pd.DataFrame(rows)
    g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
    return g


def show(label, g):
    if not len(g):
        p(f"{label:44s} no trades")
        return
    months = (g["t"].max() - g["t"].min()) / (30.44 * 24 * H_MS)
    posy = " | ".join(
        f"{y}: {g[g['year']==y]['net'].mean()*100:+.3f}%/{len(g[g['year']==y])}"
        if len(g[g["year"] == y]) else f"{y}: --" for y in YEARS)
    p(f"{label:44s} {len(g):6,} ({len(g)/months:4.0f}/mo) "
      f"{g['net'].mean()*100:+7.3f}% med {g['net'].median()*100:+6.3f}% "
      f"win {(g['net']>0).mean()*100:3.0f}%  {posy}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    p(f"HOURLY LONG-LOSER DILIGENCE — {stamp}")
    p("")

    p("A. RE-ENTRY POLICY + NEIGHBORHOOD (net of 0.14% costs)")
    base = collect(grid, tks, panel, tickers)
    show("BASE thr2% h24 (re-entry allowed)", base)
    nore = collect(grid, tks, panel, tickers, block_reentry=True)
    show("thr2% h24, one position per ticker", nore)
    for thr in (0.01, 0.03, 0.05):
        show(f"thr{thr*100:.0f}% h24 (re-entry)",
             collect(grid, tks, panel, tickers, thr=thr))
    for hold in (48, 192):
        show(f"thr2% h{hold//4}h (re-entry)",
             collect(grid, tks, panel, tickers, hold=hold))
    show("thr2% h24 costs x2",
         collect(grid, tks, panel, tickers, cost=2 * COST))

    p("")
    p("B. CONCENTRATION / TAIL (base variant)")
    nets = np.sort(base["net"].to_numpy())
    p(f"  mean {nets.mean()*100:+.3f}% | drop top-20 winners "
      f"{nets[:-20].mean()*100:+.3f}% | drop top-100 "
      f"{nets[:-100].mean()*100:+.3f}% | drop top-1% "
      f"{nets[:-max(len(nets)//100,1)].mean()*100:+.3f}%")
    p(f"  p5 {np.percentile(nets,5)*100:+.2f}% | p95 "
      f"{np.percentile(nets,95)*100:+.2f}% | max loss {nets[0]*100:+.1f}% | "
      f"max win {nets[-1]*100:+.1f}%")
    bytk = base.groupby("tk")["net"].agg(["sum", "size", "mean"]) \
               .sort_values("sum", ascending=False)
    tot = base["net"].sum()
    p(f"  top tickers by contribution (of total {tot*100:+.0f}%):")
    for tk, r in bytk.head(8).iterrows():
        p(f"    {tk:10s} {r['sum']*100:+8.0f}% over {int(r['size']):4d} "
          f"trades (mean {r['mean']*100:+.2f}%)")
    pos_tk = (bytk["mean"] > 0).mean()
    p(f"  tickers with positive mean: {pos_tk*100:.0f}% of {len(bytk)}")
    ex_top = base[~base["tk"].isin(bytk.head(3).index)]
    show("  excl top-3 tickers entirely", ex_top)

    p("")
    p("C. MOVE-DEPTH DOSE-RESPONSE (base, re-entry allowed)")
    for lo, hi in ((-0.03, -0.02), (-0.05, -0.03), (-0.08, -0.05),
                   (-1.0, -0.08)):
        g = base[(base["move"] > lo) & (base["move"] <= hi)]
        show(f"  picked move in ({lo:+.0%},{hi:+.0%}]", g)

    p("")
    p("D. SAME-EPISODE STACKING — how many of the base entries are "
      "repeat buys of the same falling coin (<24h apart)?")
    b = base.sort_values(["tk", "t"])
    new_ep = (b["tk"] != b["tk"].shift()) | (b["t"] - b["t"].shift() > 24 * H_MS)
    b["ep"] = new_ep.cumsum()
    eps = b.groupby("ep").agg(n=("net", "size"), net=("net", "mean"),
                              tk=("tk", "first"))
    p(f"  {len(b):,} trades in {len(eps):,} episodes | mean trades/episode "
      f"{eps['n'].mean():.1f} | max {eps['n'].max()}")
    p(f"  per-episode mean net {eps['net'].mean()*100:+.3f}% | episodes "
      f"positive {(eps['net']>0).mean()*100:.0f}%")
    first = b[~b.duplicated('ep')]
    show("  first-entry-of-episode only", first)

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/hourly_loser_diligence_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
