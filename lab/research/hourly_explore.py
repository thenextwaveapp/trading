#!/usr/bin/env python3
"""HOURLY-CADENCE strategy exploration (one entry per hour, full span).

Goal: a strategy that can ENTER roughly every hour (trades may be held
longer). At ~700 trades/mo the 0.14% round-trip taker cost dominates, so
the question is which hourly selection rule clears costs.

What the Invo mining says to select each hour (long side = mirror logic):
  fade profile — biggest adverse recent move, elevated natr, low in 24h
  range; crowding/chase = the losing behavior. So the family tested is
  "every hour, fade the most extreme mover in the universe", with the
  selection/conditioning axes mined from the trader data.

Engine: at every hour boundary, evaluate all 60 tickers on the last closed
15m bar, pick ONE candidate per rule, enter at that close (costs both
ways), time exit after H bars. Equal notional per trade, overlapping
positions allowed (entry cadence is the constraint, not closure).
Stats are per-trade net; no compounding (exploration lens).

Usage: python3 hourly_explore.py
Writes: reports/hourly_explore_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST, YEARS
from long_robustness import btc_regime

H_MS = 3_600_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def precompute(d):
    t, o, h, l, c, v = d["t"], d["o"], d["h"], d["l"], d["c"], d["v"]
    n = len(t)
    gap4 = np.zeros(n, bool)
    gap4[4:] = (t[4:] - t[:-4]) == 4 * M15
    vpos = pd.Series(v > 0).rolling(5).min().to_numpy() == 1
    d["alive_v"] = gap4 & vpos & (h != l) & (np.arange(n) >= 100)
    r1 = np.full(n, np.nan)
    r1[4:] = c[4:] / c[:-4] - 1                      # 1h return
    d["r1_v"] = r1
    r24 = np.full(n, np.nan)
    r24[96:] = c[96:] / c[:-96] - 1
    d["r24_v"] = r24
    mu = pd.Series(v).rolling(8).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["volr_v"] = np.where(mu > 0, v / mu, np.nan)
    cprev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - cprev), np.abs(l - cprev)))
    natr = pd.Series(tr).rolling(96).mean().to_numpy() / c
    d["natr_v"] = natr
    med30 = pd.Series(natr).rolling(2880, min_periods=960).median().to_numpy()
    d["natr_hi_v"] = natr > med30
    lo96 = pd.Series(l).rolling(96).min().to_numpy()
    hi96 = pd.Series(h).rolling(96).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["rpos_v"] = np.where(hi96 > lo96, (c - lo96) / (hi96 - lo96), np.nan)


def build_panel(tickers):
    """Align every ticker to a common hourly grid: at hour G the last
    closed bar has open time G - M15. -> dict of 2D arrays [hour, ticker]."""
    t0 = min(d["t"][0] for d in tickers.values())
    t1 = max(d["t"][-1] for d in tickers.values())
    g0 = (t0 // H_MS + 2) * H_MS
    grid = np.arange(g0, t1, H_MS)
    tks = sorted(tickers)
    shape = (len(grid), len(tks))
    panel = {k: np.full(shape, np.nan)
             for k in ("r1", "r24", "volr", "rpos", "natr")}
    panel["alive"] = np.zeros(shape, bool)
    panel["natr_hi"] = np.zeros(shape, bool)
    panel["idx"] = np.full(shape, -1, np.int64)
    for j, tk in enumerate(tks):
        d = tickers[tk]
        pos = np.searchsorted(d["t"], grid - M15)
        ok = (pos < len(d["t"])) & (d["t"][np.minimum(pos, len(d["t"]) - 1)]
                                    == grid - M15)
        ii = pos[ok]
        rows = np.nonzero(ok)[0]
        panel["idx"][rows, j] = ii
        panel["alive"][rows, j] = d["alive_v"][ii]
        panel["natr_hi"][rows, j] = d["natr_hi_v"][ii]
        for k, src in (("r1", "r1_v"), ("r24", "r24_v"), ("volr", "volr_v"),
                       ("rpos", "rpos_v"), ("natr", "natr_v")):
            panel[k][rows, j] = d[src][ii]
    return grid, tks, panel


def fwd_net(d, i, hold, side, cost):
    """Net return entering at close of bar i, time exit after `hold` bars."""
    t, c = d["t"], d["c"]
    j = i + hold
    if j >= len(t) or t[j] - t[i] != hold * M15:
        return None
    return side * (c[j] / c[i] - 1) - cost


def run(label, grid, tks, panel, tickers, pick_fn, hold=4, cost=COST,
        gate=None, summ=None):
    """pick_fn(row) -> (ticker_col, side) or None; one entry per hour."""
    alive = panel["alive"]
    nets, times, sides = [], [], []
    for r in range(len(grid)):
        if gate is not None and not gate(grid[r]):
            continue
        pick = pick_fn(r)
        if pick is None:
            continue
        j, side = pick
        d = tickers[tks[j]]
        i = panel["idx"][r, j]
        net = fwd_net(d, i, hold, side, cost)
        if net is None:
            continue
        nets.append(net)
        times.append(grid[r])
        sides.append(side)
    g = pd.DataFrame(dict(net=nets, t=times, side=sides))
    if not len(g):
        p(f"{label:40s} no trades")
        return
    g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
    posy = " | ".join(
        f"{y}: {g[g['year']==y]['net'].mean()*100:+.3f}%/{len(g[g['year']==y])}"
        if len(g[g["year"] == y]) else f"{y}: --" for y in YEARS)
    tpm = len(g) / max((g["t"].max() - g["t"].min()) / (30.44 * 24 * H_MS), 1)
    p(f"{label:40s} {len(g):6,} ({tpm:5.0f}/mo) {g['net'].mean()*100:+7.3f}% "
      f"med {g['net'].median()*100:+6.3f}% win {(g['net']>0).mean()*100:3.0f}%"
      f"  sum {g['net'].sum()*100:+8.0f}%  {posy}")
    if summ is not None:
        summ.append(dict(variant=label, n=len(g), net=g["net"].mean(),
                         tot=g["net"].sum()))
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    bull = btc_regime(tickers)
    p(f"HOURLY-CADENCE EXPLORATION — {stamp} | {len(tks)} tickers | "
      f"{len(grid):,} hourly slots 2023-01 -> 2026-10")
    p(f"entry at 15m close on the hour, taker cost {COST*100:.2f}% round "
      "trip, equal notional, time exits, overlaps allowed")
    p("")

    alive, r1 = panel["alive"], panel["r1"]
    volr, rpos = panel["volr"], panel["rpos"]
    natr_hi, r24 = panel["natr_hi"], panel["r24"]

    with np.errstate(invalid="ignore"):
        r1m = np.where(alive, r1, np.nan)

    def extreme(r, side_of, min_move, extra=None):
        """Most extreme 1h move this hour; side_of: 'loser'/'gainer'/'abs'."""
        row = r1m[r].copy()
        if extra is not None:
            row[~extra[r]] = np.nan
        if np.all(np.isnan(row)):
            return None
        if side_of == "loser":
            j = int(np.nanargmin(row))
            return (j, 1) if row[j] <= -min_move else None
        if side_of == "gainer":
            j = int(np.nanargmax(row))
            return (j, -1) if row[j] >= min_move else None
        j = int(np.nanargmax(np.abs(row)))
        if abs(row[j]) < min_move:
            return None
        return (j, -1 if row[j] > 0 else 1)

    # ---------------- census
    p("0. CENSUS — the biggest 1h move across the universe, by hour")
    mx = np.nanmax(np.abs(r1m), axis=1)
    mx = mx[~np.isnan(mx)]
    p(f"   median biggest-mover {np.median(mx)*100:.2f}% | p75 "
      f"{np.percentile(mx,75)*100:.2f}% | p90 {np.percentile(mx,90)*100:.2f}%"
      f" | hours with >=1% mover: {(mx>=0.01).mean()*100:.0f}% | >=2%: "
      f"{(mx>=0.02).mean()*100:.0f}% | >=3%: {(mx>=0.03).mean()*100:.0f}%")
    p("")

    hdr = (f"{'variant':40s} {'n':>6s} {'(rate)':>8s} {'net/tr':>7s} "
           f"{'median':>9s} {'win':>4s} {'sum':>12s}  by year")
    summ = []

    p("1. FADE THE EXTREME 1H MOVER (churn family, mined selection)")
    p(hdr)
    run("fade both sides >=1% h4 (churn)", grid, tks, panel, tickers,
        lambda r: extreme(r, "abs", 0.01), summ=summ)
    run("long loser >=1% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.01), summ=summ)
    run("short gainer >=1% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "gainer", 0.01), summ=summ)
    run("long loser >=2% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02), summ=summ)
    run("long loser >=3% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.03), summ=summ)
    run("short gainer >=2% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "gainer", 0.02), summ=summ)
    run("short gainer >=3% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "gainer", 0.03), summ=summ)

    p("")
    p("2. HOLD LADDER on the two single-sided fades (>=2%)")
    p(hdr)
    for hold, lab in ((2, "30m"), (8, "2h"), (16, "4h"), (96, "24h")):
        run(f"long loser >=2% h{lab}", grid, tks, panel, tickers,
            lambda r: extreme(r, "loser", 0.02), hold=hold, summ=summ)
    for hold, lab in ((8, "2h"), (16, "4h")):
        run(f"short gainer >=2% h{lab}", grid, tks, panel, tickers,
            lambda r: extreme(r, "gainer", 0.02), hold=hold, summ=summ)

    p("")
    p("3. MINED CONDITIONING (long-loser side): natr-high / low range / "
      "vol-spike / BTC-bear")
    p(hdr)
    run("long loser >=2% +natr-high h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02, extra=natr_hi), summ=summ)
    lowrange = rpos <= 0.3
    run("long loser >=2% +rpos<=0.3 h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02, extra=lowrange), summ=summ)
    volspike = volr >= 2
    run("long loser >=2% +vol>=2x h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02, extra=volspike), summ=summ)
    run("long loser >=2% btc-bear h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02),
        gate=lambda T: not bull(T), summ=summ)
    down24 = r24 <= -0.05
    run("long loser >=2% +24h<=-5% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02, extra=down24), summ=summ)
    up24 = r24 >= 0.05
    run("short gainer >=2% +24h>=+5% h4", grid, tks, panel, tickers,
        lambda r: extreme(r, "gainer", 0.02, extra=up24), summ=summ)

    p("")
    p("4. COST SENSITIVITY on the best-looking row (reported either way): "
      "maker-ish 0.07% and zero-cost gross")
    p(hdr)
    run("long loser >=2% h4 cost 0.07%", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02), cost=0.0007, summ=summ)
    run("long loser >=2% h4 gross", grid, tks, panel, tickers,
        lambda r: extreme(r, "loser", 0.02), cost=0.0, summ=summ)
    run("short gainer >=2% h4 cost 0.07%", grid, tks, panel, tickers,
        lambda r: extreme(r, "gainer", 0.02), cost=0.0007, summ=summ)
    run("fade both >=1% h4 gross (churn ceiling)", grid, tks, panel, tickers,
        lambda r: extreme(r, "abs", 0.01), cost=0.0, summ=summ)

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/hourly_explore_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
