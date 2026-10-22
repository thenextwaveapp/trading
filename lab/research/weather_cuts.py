#!/usr/bin/env python3
"""Every book's backtest trades x the weather almanac.

For each rule, generate full-history trades plus same-timestamp stand-ins
(median-1h-return coin and BTC, same side/hold/cost). Join each trade to
the hourly weather row at entry, bucket by every instrument in almanac
quintiles, and rank instruments by how far apart the extreme quintiles'
SPREAD (pick minus median-coin stand-in) sits — spread, not raw net, so
market move can't pose as selection edge. Full tables to reports/.
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
sys.path.insert(2, ROOT)

from regime_switch_backtest import load_full                    # noqa: E402
from hourly_explore import precompute, build_panel              # noqa: E402

M15 = 900_000
COST_L = 0.0014          # loser/capit research convention
COST_S = 0.0019          # pump-short research convention
OUT = []


def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def alive_win(d, i, n):
    return (i >= n and d["t"][i] - d["t"][i - n] == n * M15
            and (d["v"][i - n:i + 1] > 0).all()
            and d["h"][i] != d["l"][i])


def texit(d, i, hold):
    j = i + hold
    if j >= len(d["t"]) or d["t"][j] - d["t"][i] != hold * M15:
        return None
    return d["c"][j] / d["c"][i] - 1


# ------------------------------------------------------------ generators
def gen_loser(tickers, grid, tks, panel, thr, hold):
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    rows = []
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmin(row))
        if np.isnan(row[j]) or row[j] > -thr:
            continue
        d = tickers[tks[j]]
        m = texit(d, panel["idx"][r, j], hold)
        if m is None:
            continue
        rows.append(dict(t=int(grid[r]), r=r, side=1, net=m - COST_L))
    return rows


def gen_pump(tickers, grid, tks, panel, hold):
    rows = []
    for tk, d in tickers.items():
        t, c, v = d["t"], d["c"], d["v"]
        last_exit = 0
        for i in range(20, len(t)):
            if t[i] < grid[0] or t[i] <= last_exit:
                continue
            if not alive_win(d, i, 16):
                continue
            if c[i] / c[i - 16] - 1 < 0.12 or c[i] >= c[i - 1]:
                continue
            mu = v[i - 8:i].mean()
            if mu <= 0 or v[i] / mu < 2.0:
                continue
            m = texit(d, i, hold)
            if m is None:
                continue
            last_exit = t[i + hold] if i + hold < len(t) else t[-1]
            rows.append(dict(t=int(t[i]), side=-1, net=-m - COST_S))
    return rows


def gen_capit(tickers, grid, tks, panel, depth, hold):
    rows = []
    for tk, d in tickers.items():
        t, c = d["t"], d["c"]
        last_exit = 0
        r24 = np.full(len(c), np.nan)
        r24[96:] = c[96:] / c[:-96] - 1
        cond = r24 <= -depth
        for i in range(97, len(t)):
            if t[i] < grid[0] or t[i] <= last_exit:
                continue
            if not cond[i] or cond[i - 1]:
                continue
            if not alive_win(d, i, 96):
                continue
            m = texit(d, i, hold)
            if m is None:
                continue
            last_exit = t[i + hold] if i + hold < len(t) else t[-1]
            rows.append(dict(t=int(t[i]), side=1, net=m - COST_L))
    return rows


# ------------------------------------------------------------ stand-ins
def add_standins(rows, tickers, grid, tks, panel, hold, cost):
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    gidx = {int(t): r for r, t in enumerate(grid)}
    btc = tickers["BTC"]
    for tr in rows:
        r = gidx.get(tr["t"] // 3_600_000 * 3_600_000, None)
        if r is None:
            r = int(np.searchsorted(grid, tr["t"], side="right")) - 1
        tr["row"] = r
        row = r1m[r]
        med = None
        al = np.where(~np.isnan(row))[0]
        if len(al):
            mj = al[np.argsort(row[al])[len(al) // 2]]
            med = texit(tickers[tks[mj]], panel["idx"][r, mj], hold)
        bi = int(np.searchsorted(btc["t"], tr["t"], side="right")) - 1
        b = texit(btc, bi, hold) if bi >= 0 else None
        s = tr["side"]
        tr["med"] = None if med is None else s * med - cost
        tr["btc"] = None if b is None else s * b - cost
    return [tr for tr in rows if tr["med"] is not None]


# ------------------------------------------------------------ cuts
def cut_book(name, rows, alm, inst):
    g = pd.DataFrame(rows)
    g["spread"] = g["net"] - g["med"]
    arow = np.searchsorted(alm["t"].to_numpy(), g["t"].to_numpy(),
                           side="right") - 1
    g = g[arow >= 0]
    arow = arow[arow >= 0]
    months = (g["t"].max() - g["t"].min()) / (30.44 * 86_400_000)
    p(f"\n===== {name}: {len(g):,} trades ({len(g)/months:.0f}/mo) | "
      f"net {g['net'].mean()*100:+.3f}% | stand-in(med) "
      f"{g['med'].mean()*100:+.3f}% | spread {g['spread'].mean()*100:+.3f}%")
    scores = []
    min_cell = max(30, len(g) // 25)
    for col in inst:
        vals = alm[col].to_numpy()[arow]
        m = np.isfinite(vals)
        if m.sum() < 5 * min_cell:
            continue
        try:
            q = pd.qcut(pd.Series(vals[m]), 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        if q.nunique() < 5:
            continue
        sub = g[m].copy()
        sub["q"] = q.to_numpy()
        cells = sub.groupby("q").agg(n=("spread", "size"),
                                     sp=("spread", "mean"),
                                     net=("net", "mean"))
        if cells["n"].min() < min_cell:
            continue
        lo, hi = cells["sp"].iloc[0], cells["sp"].iloc[-1]
        se = sub["spread"].std() / np.sqrt(cells["n"].min())
        scores.append((abs(hi - lo) / max(se, 1e-9), col, cells))
    scores.sort(key=lambda x: -x[0])
    p(f"top instruments by |spread(q5)-spread(q1)| / se  "
      f"(cells >= {min_cell} trades):")
    for sc, col, cells in scores[:12]:
        row = "  ".join(f"q{i+1} {cells['sp'].iloc[i]*100:+.2f}%/"
                        f"{cells['net'].iloc[i]*100:+.2f}%"
                        for i in range(len(cells)))
        p(f"  {col:22s} score {sc:5.1f}   {row}")
    p("  (each cell: spread/net. q1 = lowest instrument quintile)")
    return scores


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alm = pd.read_csv(os.path.join(ROOT, "backtest", "weather.csv.gz"))
    inst = [c for c in alm.columns if c != "t"]
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    grid = np.asarray(grid, dtype=np.int64)
    p(f"WEATHER CUTS — {stamp}")
    p(f"almanac: {len(alm):,} rows x {len(inst)} instruments | "
      f"metric: spread = pick - median-coin stand-in (same side/hold/cost)")

    books = [
        ("loser thr2 h24",  gen_loser(tickers, grid, tks, panel, 0.02, 96),
         96, COST_L),
        ("loser thr3 h24",  gen_loser(tickers, grid, tks, panel, 0.03, 96),
         96, COST_L),
        ("pump-short h4",   gen_pump(tickers, grid, tks, panel, 16),
         16, COST_S),
        ("pump-short h24",  gen_pump(tickers, grid, tks, panel, 96),
         96, COST_S),
        ("capit20 h24",     gen_capit(tickers, grid, tks, panel, 0.20, 96),
         96, COST_L),
        ("capit20 h48",     gen_capit(tickers, grid, tks, panel, 0.20, 192),
         192, COST_L),
    ]
    for name, rows, hold, cost in books:
        rows = add_standins(rows, tickers, grid, tks, panel, hold, cost)
        cut_book(name, rows, alm, inst)

    out = os.path.join(ROOT, "reports",
                       f"weather_cuts_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    open(out, "w").write("\n".join(OUT) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
