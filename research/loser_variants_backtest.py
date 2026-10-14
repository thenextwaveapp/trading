#!/usr/bin/env python3
"""Loser-engine variant grid: exits, entry filters, re-entry policy.

Engine (matches fleet hourly_loser): every hour, long the biggest 1h
loser <= -thr, enter at close. Baseline exit: 24h time, no stop.
Exits simulated on 15m closes (the bot acts on closed bars).

Phases:
  A  exit variants          (thr 2%, no filter, re-entry allowed)
  B  entry filters          (x time96 and trail 3/3)
  C  re-entry policies      (x time96 and trail 3/3)
  D  expectancy by stack depth (baseline rule)

Usage: python3 loser_variants_backtest.py
Writes: reports/loser_variants_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST, YEARS
from hourly_explore import precompute, build_panel, H_MS

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def path_exit(d, i, hold, ex):
    """Net return for exit spec `ex`, acting on 15m closes. None = gap."""
    t, c = d["t"], d["c"]
    j = i + hold
    if j >= len(t) or t[j] - t[i] != hold * M15:
        return None
    entry = c[i]
    w = c[i + 1:j + 1]
    r = w / entry - 1
    kind = ex["kind"]
    if kind == "time":
        return r[-1] - COST, "time"
    if kind == "partial":
        half = path_exit(d, i, hold, {"kind": "tp", "x": ex["x"]})
        return 0.5 * half[0] + 0.5 * (r[-1] - COST), "partial"
    if kind == "sl":
        hit = r <= -ex["x"]
    elif kind == "tp":
        hit = r >= ex["x"]
    elif kind == "be":
        peak = np.maximum.accumulate(r)
        hit = (peak >= ex["arm"]) & (r <= 0)
    elif kind == "trail":
        peak = np.maximum.accumulate(r)
        hit = (peak >= ex["arm"]) & ((1 + r) <= (1 + peak) * (1 - ex["w"]))
    else:
        raise ValueError(kind)
    k = int(np.argmax(hit))
    if hit[k]:
        return r[k] - COST, kind
    return r[-1] - COST, "time"


def collect(grid, tks, panel, tickers, ex, thr=0.02, hold=96,
            f_r24=None, f_rpos=None, reentry="allow", gap=0.05):
    """One entry per hour: biggest 1h loser passing filters/re-entry."""
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    open_until = {}          # tk -> expiry ms (baseline hold expiry)
    last_entry = {}          # tk -> entry close while open
    rows = []
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        T = grid[r]
        for j in np.argsort(row):
            if np.isnan(row[j]) or row[j] > -thr:
                break
            if f_r24 is not None and not panel["r24"][r, j] <= f_r24:
                continue
            if f_rpos is not None and not panel["rpos"][r, j] <= f_rpos:
                continue
            tk = tks[j]
            held = open_until.get(tk, 0) > T
            if reentry == "block" and held:
                continue
            d = tickers[tk]
            i = panel["idx"][r, j]
            if reentry == "gap" and held and \
                    d["c"][i] > last_entry[tk] * (1 - gap):
                continue
            res = path_exit(d, i, hold, ex)
            if res is None:
                continue
            open_until[tk] = T + hold * M15
            last_entry[tk] = d["c"][i]
            rows.append(dict(t=T, tk=tk, net=res[0], kind=res[1]))
            break
    g = pd.DataFrame(rows)
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
    return g


def show(label, g):
    if not len(g):
        p(f"{label:40s} no trades")
        return
    months = (g["t"].max() - g["t"].min()) / (30.44 * 24 * H_MS)
    posy = " | ".join(
        f"{y}: {g[g['year']==y]['net'].mean()*100:+.3f}%/{len(g[g['year']==y])}"
        if len(g[g["year"] == y]) else f"{y}: --" for y in YEARS)
    kinds = g["kind"].value_counts(normalize=True)
    kstr = " ".join(f"{k}:{v*100:.0f}%" for k, v in kinds.items())
    p(f"{label:40s} {len(g):6,} ({len(g)/months:4.0f}/mo) "
      f"{g['net'].mean()*100:+7.3f}% med {g['net'].median()*100:+6.3f}% "
      f"win {(g['net']>0).mean()*100:3.0f}%  [{kstr}]")
    p(f"{'':40s} {posy}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    p(f"LOSER VARIANTS — {stamp}")
    p(f"cost {COST*100:.2f}% rt | thr 2% hourly biggest-loser | hold<=24h")
    p("")

    E0 = {"kind": "time"}
    TRAIL = {"kind": "trail", "arm": 0.03, "w": 0.03}

    p("A. EXITS (no filter, re-entry allowed)")
    for label, ex, hold in [
        ("time 24h (baseline)",            E0, 96),
        ("time 12h",                       E0, 48),
        ("time 6h",                        E0, 24),
        ("stop -5%",                       {"kind": "sl", "x": 0.05}, 96),
        ("stop -8%",                       {"kind": "sl", "x": 0.08}, 96),
        ("tp +4%",                         {"kind": "tp", "x": 0.04}, 96),
        ("tp +6%",                         {"kind": "tp", "x": 0.06}, 96),
        ("breakeven after +3%",            {"kind": "be", "arm": 0.03}, 96),
        ("trail arm+2% w2%",               {"kind": "trail", "arm": 0.02, "w": 0.02}, 96),
        ("trail arm+3% w3%",               TRAIL, 96),
        ("trail arm+3% w5%",               {"kind": "trail", "arm": 0.03, "w": 0.05}, 96),
        ("partial: half tp+4%, half time", {"kind": "partial", "x": 0.04}, 96),
    ]:
        show(label, collect(grid, tks, panel, tickers, ex, hold=hold))
    p("")

    p("B. ENTRY FILTERS (x time96 / trail3-3)")
    for flabel, kw in [
        ("r24<=+10%", dict(f_r24=0.10)),
        ("r24<=+20%", dict(f_r24=0.20)),
        ("rpos<=0.5", dict(f_rpos=0.5)),
        ("rpos<=0.75", dict(f_rpos=0.75)),
        ("thr 3%", dict(thr=0.03)),
        ("thr 5%", dict(thr=0.05)),
    ]:
        show(f"{flabel} | time96", collect(grid, tks, panel, tickers, E0, **kw))
        show(f"{flabel} | trail", collect(grid, tks, panel, tickers, TRAIL, **kw))
    p("")

    p("C. RE-ENTRY (x time96 / trail3-3)")
    for rlabel, kw in [
        ("block while open", dict(reentry="block")),
        ("re-entry only -5% below", dict(reentry="gap", gap=0.05)),
    ]:
        show(f"{rlabel} | time96", collect(grid, tks, panel, tickers, E0, **kw))
        show(f"{rlabel} | trail", collect(grid, tks, panel, tickers, TRAIL, **kw))
    p("")

    p("D. EXPECTANCY BY STACK DEPTH (baseline rule)")
    g = collect(grid, tks, panel, tickers, E0)
    opens = {}
    depths = []
    for _, tr in g.iterrows():
        q = opens.setdefault(tr["tk"], [])
        q[:] = [e for e in q if e > tr["t"]]
        depths.append(len(q) + 1)
        q.append(tr["t"] + 96 * M15)
    g["depth"] = depths
    for dep, gg in g.groupby(g["depth"].clip(upper=4)):
        lab = f"depth {dep}" + ("+" if dep == 4 else "")
        p(f"  {lab:10s} {len(gg):6,}  {gg['net'].mean()*100:+7.3f}% "
          f"med {gg['net'].median()*100:+6.3f}% win {(gg['net']>0).mean()*100:3.0f}%")
    p("")

    os.makedirs("reports", exist_ok=True)
    out = f"reports/loser_variants_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt"
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
