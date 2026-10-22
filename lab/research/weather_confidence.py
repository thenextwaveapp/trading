#!/usr/bin/env python3
"""Confidence checks on the weather-cut findings.

1. Do the favorable cells of different books share calendar days?
   (one phenomenon vs several)
2. Does each book's favorable-cell advantage hold year by year?
3. Episode-level sample size: cluster favorable-cell trades (3-day gap),
   per-episode spread, share of episodes positive.
4. The odd lead: loser x btc_fund9 q5 — by year.
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_here)
sys.path.insert(0, _here)
sys.path.insert(1, os.path.join(_here, "_archive"))

from regime_switch_backtest import load_full                    # noqa: E402
from hourly_explore import precompute, build_panel              # noqa: E402
from weather_cuts import (gen_loser, gen_pump, gen_capit,       # noqa: E402
                          add_standins, COST_L, COST_S, OUT, p)

def qmask(alm, arow, col, want_q, nq=5):
    vals = alm[col].to_numpy()[arow]
    m = np.isfinite(vals)
    q = pd.Series(np.full(len(vals), -1))
    q[m] = pd.qcut(pd.Series(vals[m]), nq, labels=False, duplicates="drop")
    return (q == want_q).to_numpy()


def episodes(ts, gap_days=3):
    ds = sorted(set(pd.to_datetime(ts, unit="ms").dt.date))
    eps, cur = [], [ds[0]]
    for a, b in zip(ds, ds[1:]):
        (cur.append(b) if (b - a).days <= gap_days else
         (eps.append(cur), cur := [b]))
    eps.append(cur)
    return eps, ds


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alm = pd.read_csv(os.path.join(ROOT, "backtest", "weather.csv.gz"))
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    grid = np.asarray(grid, dtype=np.int64)
    p(f"WEATHER CONFIDENCE CHECKS — {stamp}\n")

    # book -> (trades, favorable instrument, favorable quintile)
    specs = [
        ("loser",  gen_loser(tickers, grid, tks, panel, 0.02, 96), 96,
         COST_L, "uni_med24", 0),
        ("capit",  gen_capit(tickers, grid, tks, panel, 0.20, 96), 96,
         COST_L, "btc_rsi14_1h", 0),
        ("pump",   gen_pump(tickers, grid, tks, panel, 96), 96,
         COST_S, "uni_med_rpos", 0),
    ]
    fav_days, frames = {}, {}
    for name, rows, hold, cost, col, wq in specs:
        rows = add_standins(rows, tickers, grid, tks, panel, hold, cost)
        g = pd.DataFrame(rows)
        g["spread"] = g["net"] - g["med"]
        arow = np.searchsorted(alm["t"].to_numpy(), g["t"].to_numpy(),
                               side="right") - 1
        g, arow = g[arow >= 0], arow[arow >= 0]
        g["fav"] = qmask(alm, arow, col, wq)
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        g["day"] = pd.to_datetime(g["t"], unit="ms").dt.date
        frames[name] = (g, col)
        fav_days[name] = set(g[g["fav"]]["day"])

    p("1. CALENDAR OVERLAP of favorable cells (jaccard; days)")
    names = list(fav_days)
    flush = set(pd.to_datetime(
        alm[alm["btc_r24"] <= -0.05]["t"], unit="ms").dt.date)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ja = len(fav_days[a] & fav_days[b]) / len(fav_days[a] | fav_days[b])
            p(f"   {a:6s} x {b:6s}  jaccard {ja:.2f}  "
              f"({len(fav_days[a])}d, {len(fav_days[b])}d, "
              f"shared {len(fav_days[a] & fav_days[b])}d)")
    for a in names:
        p(f"   {a:6s} x btc-flush days: {len(fav_days[a] & flush)} of "
          f"{len(fav_days[a])} favorable days are flush days")

    p("\n2. FAVORABLE-CELL SPREAD BY YEAR (fav vs rest)")
    for name, (g, col) in frames.items():
        p(f"   {name} ({col} q1):")
        for y in sorted(g["year"].unique()):
            s = g[g["year"] == y]
            f, r = s[s["fav"]], s[~s["fav"]]
            p(f"     {y}  fav {f['spread'].mean()*100 if len(f) else float('nan'):+7.3f}%/{len(f):4d}"
              f"   rest {r['spread'].mean()*100:+7.3f}%/{len(r):5d}")

    p("\n3. EPISODE-LEVEL SAMPLE (favorable cells, 3-day gap clustering)")
    for name, (g, col) in frames.items():
        f = g[g["fav"]]
        if not len(f):
            continue
        eps, _ = episodes(f["t"])
        day_mean = f.groupby("day")["spread"].mean()
        ep_means = []
        for e in eps:
            days = set(e)
            ep_means.append(day_mean[[d in days for d in day_mean.index]].mean())
        ep_means = pd.Series(ep_means)
        p(f"   {name:6s} {len(f):5,} trades -> {len(eps):3d} episodes | "
          f"per-episode spread mean {ep_means.mean()*100:+.2f}% "
          f"med {ep_means.median()*100:+.2f}% | episodes>0: "
          f"{(ep_means > 0).mean()*100:.0f}%")

    p("\n4. loser x btc_fund9, HIGHEST-funding quintile, by year")
    g, _ = frames["loser"]
    arow = np.searchsorted(alm["t"].to_numpy(), g["t"].to_numpy(),
                           side="right") - 1
    g = g.copy()
    g["f9"] = qmask(alm, arow, "btc_fund9", 4)
    for y in sorted(g["year"].unique()):
        s = g[g["year"] == y]
        f, r = s[s["f9"]], s[~s["f9"]]
        p(f"     {y}  fund-q5 {f['spread'].mean()*100 if len(f) else float('nan'):+7.3f}%/{len(f):4d}"
          f"   rest {r['spread'].mean()*100:+7.3f}%/{len(r):5d}")

    out = os.path.join(ROOT, "reports",
                       f"weather_confidence_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    open(out, "w").write("\n".join(OUT) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
