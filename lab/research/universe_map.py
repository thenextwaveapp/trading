#!/usr/bin/env python3
"""UNIVERSE MAP — per-coin expectancy of the two core rules on EVERY
Binance perp, 2025-26 window. Answers: do positive-expectancy coins
cluster in the Invo 60, or is there another universe out there?

Per coin, no gates (raw signal expectancy, comparable across coins):
  pump-short: rule P signals (>=12%/4h, first red, vol>=2x), short,
              24h hold, stop at 4h high
  capit-long: -20%/24h fresh cross, long, 48h hold, no stop

Output: in/out positive-share, liquidity deciles, best outsiders (n>=5),
worst insiders.

Usage: python3 research/universe_map.py
Writes: reports/universe_map_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, sig_pump, sig_capit, resolve
from super_larry_wide import load_wide_era
from random_degen_test import TRADFI

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def coin_stats(tk, d):
    precompute(d)
    out = dict(tk=tk, dv=float(np.median(d["c"] * d["v"])))
    ii, _ = sig_pump(d)
    nets = []
    last = -10**18
    for i in ii:
        if d["t"][i] < last:
            continue
        net, exit_t, kind = resolve(d, i, "short", 96, "4hhigh", 1)
        nets.append(net)
        last = exit_t
    out["s_n"], out["s_avg"] = len(nets), (np.mean(nets) if nets else np.nan)
    ii, _ = sig_capit(d, drop=0.20)
    nets = []
    last = -10**18
    for i in ii:
        if d["t"][i] < last:
            continue
        net, exit_t, kind = resolve(d, i, "long", 192, "none", 1)
        nets.append(net)
        last = exit_t
    out["c_n"], out["c_avg"] = len(nets), (np.mean(nets) if nets else np.nan)
    return out


def share(rows, key_n, key_avg, min_n=3):
    rs = [r for r in rows if r[key_n] >= min_n]
    pos = [r for r in rs if r[key_avg] > 0]
    return len(rs), len(pos)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"UNIVERSE MAP — {stamp} | every perp, 2025-26 window, no gates")
    p("")
    curated, _ = load("backtest/r60_candles_15m.csv.gz",
                      "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))
    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    wide = {tk: d for tk, d in wide.items() if tk not in TRADFI}

    rows_in = [coin_stats(tk, d) for tk, d in curated.items()]
    rows_out = [coin_stats(tk, d) for tk, d in wide.items()]
    p(f"coins: {len(rows_in)} Invo-60 | {len(rows_out)} outside "
      "(crypto perps, TradFi excluded)")
    p("")

    p("POSITIVE-EXPECTANCY SHARE (coins with >= 3 trades)")
    for lab, kn, ka in [("pump-short", "s_n", "s_avg"),
                        ("capit-long", "c_n", "c_avg")]:
        ni, pi = share(rows_in, kn, ka)
        no, po = share(rows_out, kn, ka)
        p(f"  {lab:11s}  Invo60: {pi}/{ni} positive ({pi/ni*100 if ni else 0:3.0f}%)"
          f"   outside: {po}/{no} positive ({po/no*100 if no else 0:3.0f}%)")
    p("")

    p("OUTSIDE COINS BY LIQUIDITY DECILE (median 15m $vol) — capit-long")
    rs = sorted([r for r in rows_out if r["c_n"] >= 3],
                key=lambda r: -r["dv"])
    k = max(1, len(rs) // 5)
    for q in range(5):
        chunk = rs[q * k:(q + 1) * k]
        if not chunk:
            continue
        avg = np.nanmean([r["c_avg"] for r in chunk])
        pos = sum(1 for r in chunk if r["c_avg"] > 0)
        p(f"  Q{q+1} (${chunk[-1]['dv']/1e3:,.0f}k+): {pos}/{len(chunk)} pos, "
          f"mean avg {avg*100:+.2f}%")
    p("")

    for lab, kn, ka in [("pump-short", "s_n", "s_avg"),
                        ("capit-long", "c_n", "c_avg")]:
        best = sorted([r for r in rows_out if r[kn] >= 5],
                      key=lambda r: -r[ka])[:15]
        p(f"BEST OUTSIDERS — {lab} (n>=5)")
        for r in best:
            p(f"  {r['tk']:14s} n={r[kn]:3d}  avg {r[ka]*100:+6.2f}%  "
              f"${r['dv']/1e3:,.0f}k/15m")
        worst = sorted([r for r in rows_in if r[kn] >= 5],
                       key=lambda r: r[ka])[:8]
        p(f"WORST INSIDERS — {lab} (n>=5)")
        for r in worst:
            p(f"  {r['tk']:14s} n={r[kn]:3d}  avg {r[ka]*100:+6.2f}%  "
              f"${r['dv']/1e3:,.0f}k/15m")
        p("")

    fname = ("reports/universe_map_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
