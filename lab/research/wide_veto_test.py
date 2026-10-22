#!/usr/bin/env python3
"""WIDE VETO + UNIVERSE BOUNDARY TEST — the 900-perp questions.

1. Build a merged 2025+ cache: r60 (curated 60) + wide (the other 824,
   incl. delisted), trimmed to t >= 2024-12-15 to bound memory.
2. Veto test at scale: base vs veto on the full universe, 2025-01..today.
   Placebo p-value on the vetoed set (the 23-trade problem, solved).
3. Universe boundary: base avg net per liquidity tier — curated 60 vs
   the expansion, and the expansion split by median 15m dollar volume.

Usage: python3 research/wide_veto_test.py
Writes: reports/wide_veto_test_<stamp>.txt, backtest/full25_{15m,1h}.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load
from degen_derby import precompute, sig_pump
from regime_switch_backtest import pump_events, make_dial
from veto_fh_test import resolve_trade, run_arm
from backtest import M15

T_TRIM = int(datetime(2024, 12, 15, tzinfo=timezone.utc).timestamp() * 1000)
T0 = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
T1 = int(datetime(2026, 12, 31, tzinfo=timezone.utc).timestamp() * 1000)

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def build_merged():
    for iv in ("15m", "1h"):
        out = f"backtest/full25_{iv}.csv.gz"
        if os.path.exists(out):
            p(f"{out} exists, reusing")
            continue
        p(f"building {out} ...")
        parts = []
        for src in (f"backtest/r60_candles_{iv}.csv.gz", f"backtest/wide_{iv}.csv.gz"):
            for chunk in pd.read_csv(src, chunksize=5_000_000):
                parts.append(chunk[chunk["t"] >= T_TRIM])
        df = pd.concat(parts, ignore_index=True)
        df.to_csv(out, index=False, compression="gzip")
        p(f"  {len(df):,} rows")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"WIDE VETO + UNIVERSE BOUNDARY — {stamp}")
    build_merged()
    tickers, _ = load("backtest/full25_15m.csv.gz", "backtest/full25_1h.csv.gz")
    p(f"loaded {len(tickers)} tickers (2024-12-15..today)")
    for d in tickers.values():
        precompute(d)
    dial = make_dial(*pump_events(tickers), 30, 0.0)
    p("")

    # ---------------- base vs veto, full universe
    p("ARMS (full universe, 2025-01..today, fleet costs + 0.3% stop slip):")
    for name, veto in [("base", False), ("veto", True)]:
        r = run_arm(tickers, dial, T0, T1, veto=veto, fh=False)
        p(f"  {name:5s} trades {r['n']:5d} | avg {r['avg']*100:+.3f}% | "
          f"win {r['win']*100:.1f}% | eq {r['ret']*100:+.2f}% | dd {r['maxdd']*100:.1f}%")
    p("")

    # ---------------- trade-level: vetoed vs kept + placebo (per-ticker lock)
    rows = []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        rows += [(d["t"][i] + M15, tk, i) for i in ii if T0 <= d["t"][i] + M15 < T1]
    rows.sort()
    open_until = {}
    recs = []
    for t_sig, tk, i in rows:
        if open_until.get(tk, 0) > t_sig:
            continue
        net, exit_t, kind, _ = resolve_trade(tickers[tk], i, i)
        open_until[tk] = exit_t
        s, n, m = dial(t_sig)
        vet = m is not None and m == m and m > 0.02
        recs.append((tk, t_sig, net, vet))
    df = pd.DataFrame(recs, columns=["tk", "t", "net", "vetoed"])
    v, k = df[df.vetoed], df[~df.vetoed]
    p(f"TRADE-LEVEL (no conc cap): {len(df)} trades, vetoed {len(v)}")
    p(f"  vetoed avg {v.net.mean()*100:+.3f}% | kept avg {k.net.mean()*100:+.3f}%")
    rng = np.random.default_rng(7)
    nets = df.net.to_numpy()
    draws = np.array([nets[rng.choice(len(nets), len(v), replace=False)].mean()
                      for _ in range(20000)])
    p(f"  placebo: random {len(v)}-subsets <= vetoed avg in "
      f"{(draws <= v.net.mean()).mean()*100:.3f}% of 20,000 draws")
    mo = df[df.vetoed].assign(month=pd.to_datetime(df[df.vetoed].t, unit='ms').dt.strftime('%Y-%m'))
    p(f"  veto fires by month: {dict(mo.groupby('month').size())}")
    p("")

    # ---------------- universe boundary: base edge by liquidity tier
    import json
    u60 = set(json.load(open("paper/universe60.json")))
    dv = {}
    for tk, d in tickers.items():
        dv[tk] = float(np.nanmedian(d["v"] * d["c"]))
    df["curated"] = df.tk.isin(u60)
    df["dv"] = df.tk.map(dv)
    exp = df[~df.curated].copy()
    if len(exp):
        qs = exp.dv.quantile([0.33, 0.66]).to_numpy()
        exp["tier"] = np.where(exp.dv >= qs[1], "exp-high",
                        np.where(exp.dv >= qs[0], "exp-mid", "exp-low"))
    p("UNIVERSE BOUNDARY (base-style trades, 2025-01..today):")
    cur = df[df.curated]
    p(f"  curated-60     : {len(cur):5d} trades | avg {cur.net.mean()*100:+.3f}% | win {(cur.net>0).mean()*100:.0f}%")
    for tier in ("exp-high", "exp-mid", "exp-low"):
        g = exp[exp.tier == tier]
        med = g.dv.median() / 1e3
        p(f"  {tier:15s}: {len(g):5d} trades | avg {g.net.mean()*100:+.3f}% | "
          f"win {(g.net>0).mean()*100:.0f}% | median 15m $vol ~${med:,.0f}k")
    p("")
    p("(exp tiers = expansion universe split by median 15m dollar volume terciles)")

    fname = f"reports/wide_veto_test_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
