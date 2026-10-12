#!/usr/bin/env python3
"""Analyses over a fill ledger (no re-backtesting needed).

1. Bracket grid-search: re-price every stored fill under TP x SL x hold grid.
2. Adverse selection: filled vs unfilled orders' post-signal returns.
3. Score autopsy: outcomes by model-score decile.
4. Block bootstrap (by week): CI on net per trade for the chosen bracket.

Usage: python3 ledger_analysis.py backtest/ledger_run2.csv.gz
Writes: reports/ledger_analysis_<stamp>.txt
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest2 import MAKER, TAKER, SLIP

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def reprice(row_paths, natr, tp_m, sl_m, hold):
    """Re-simulate the bracket on a stored path. Returns (net, kind)."""
    hs, ls, cs = row_paths
    tp, sl = tp_m * natr, -sl_m * natr
    n = min(hold, len(hs))
    for j in range(n):
        if ls[j] <= sl:
            return sl - (MAKER + TAKER + SLIP), "sl"
        if hs[j] >= tp:
            return tp - (MAKER + MAKER), "tp"
    return cs[n - 1] - (MAKER + TAKER + SLIP), "time"


def main(path):
    led = pd.read_csv(path)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"LEDGER ANALYSIS — {stamp}  (source: {path})")
    p(f"orders: {len(led):,} | filled: {led['filled'].sum():,} | "
      f"blocked: {(led['blocked']!='').sum() if led['blocked'].dtype==object else (led['blocked'].notna()&(led['blocked']!='')).sum()}")

    fills = led[(led["filled"] == 1) & led["path_h"].notna() & (led["path_h"] != "")].copy()
    paths = []
    for r in fills.itertuples():
        s = int(r.side)
        h = np.array([float(x) for x in r.path_h.split(";")])
        l = np.array([float(x) for x in r.path_l.split(";")])
        c = np.array([float(x) for x in r.path_c.split(";")])
        # direction-adjust: favorable = +
        if s == 1:
            paths.append((h, l, c))
        else:
            paths.append((-l, -h, -c))
    natrs = fills["natr"].to_numpy(float)

    # ---- 1. bracket grid ----
    p("")
    p("=" * 78)
    p("1. BRACKET GRID (net %/trade, repriced on identical fills)")
    tps = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    sls = [0.5, 0.75, 1.0, 1.5]
    holds = [4, 8, 12, 16, 24]
    best = None
    p("   rows=TP x cols=SL, hold=8:")
    p("        " + "".join(f"  SL{s:<5}" for s in sls))
    grid_rows = {}
    for hold in holds:
        for tp in tps:
            for sl in sls:
                nets = [reprice(pt, na, tp, sl, hold)[0] for pt, na in zip(paths, natrs)]
                mu = float(np.mean(nets))
                grid_rows[(tp, sl, hold)] = mu
                if best is None or mu > best[0]:
                    best = (mu, tp, sl, hold, nets)
    for tp in tps:
        p(f"  TP{tp:<4}" + "".join(f"  {grid_rows[(tp, sl, 8)]*100:+6.3f}" for sl in sls))
    p("\n  best combos across full grid (incl. hold):")
    for (tp, sl, hold), mu in sorted(grid_rows.items(), key=lambda kv: -kv[1])[:8]:
        p(f"    TP {tp} / SL {sl} / hold {hold}: {mu*100:+.3f}%/trade")
    mu, tp_b, sl_b, hold_b, nets_b = best
    neigh = [grid_rows.get(k) for k in
             [(t2, s2, hold_b) for t2 in tps for s2 in sls
              if abs(tps.index(t2) - tps.index(tp_b)) <= 1 and abs(sls.index(s2) - sls.index(sl_b)) <= 1]]
    neigh = [x for x in neigh if x is not None]
    p(f"\n  CHOSEN: TP {tp_b} / SL {sl_b} / hold {hold_b} -> {mu*100:+.3f}%/trade "
      f"(neighbor mean {np.mean(neigh)*100:+.3f}% -> {'stable' if np.mean(neigh) > 0 else 'FRAGILE'})")
    p(f"  run #2 bracket (1.5/1.0/8) on same fills: {grid_rows[(1.5,1.0,8)]*100:+.3f}%/trade")

    # ---- 2. adverse selection ----
    p("")
    p("=" * 78)
    p("2. ADVERSE SELECTION (post-signal 2h return from signal price, direction-adjusted)")
    tradeable = led[led["blocked"].fillna("") == ""] if led["blocked"].dtype == object else led
    f1 = tradeable[tradeable["filled"] == 1]["sig_fwd2h"].dropna()
    f0 = tradeable[tradeable["filled"] == 0]["sig_fwd2h"].dropna()
    p(f"  filled   (n={len(f1):,}): mean {f1.mean()*100:+.3f}%")
    p(f"  unfilled (n={len(f0):,}): mean {f0.mean()*100:+.3f}%")
    p("  unfilled >> filled would mean the limit only fills on the worse trades.")

    # ---- 3. score autopsy ----
    p("")
    p("=" * 78)
    p("3. SCORE AUTOPSY (does the model score rank outcomes among fills?)")
    fills["net_run2"] = [reprice(pt, na, 1.5, 1.0, 8)[0] for pt, na in zip(paths, natrs)]
    try:
        fills["dec"] = pd.qcut(fills["score"], 5, labels=False, duplicates="drop")
        for d, g in fills.groupby("dec"):
            p(f"  score Q{int(d)+1}: n={len(g):4,}  net {g['net_run2'].mean()*100:+.3f}%  "
              f"(score {g['score'].min():.3f}-{g['score'].max():.3f})")
    except ValueError:
        p("  score spread too narrow for deciles")

    # ---- 4. block bootstrap ----
    p("")
    p("=" * 78)
    p("4. BLOCK BOOTSTRAP (by week) — chosen bracket net/trade")
    fills["week"] = pd.to_datetime(fills["t_signal"], unit="ms").dt.strftime("%Y-%U")
    fills["net_best"] = nets_b
    weeks = fills["week"].unique()
    rng = np.random.default_rng(7)
    boots = []
    for _ in range(2000):
        pick = rng.choice(weeks, len(weeks), replace=True)
        sample = pd.concat([fills[fills["week"] == w]["net_best"] for w in pick])
        boots.append(sample.mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p(f"  mean {fills['net_best'].mean()*100:+.3f}%  95% CI [{lo*100:+.3f}%, {hi*100:+.3f}%]  "
      f"({'excludes' if lo > 0 or hi < 0 else 'INCLUDES'} zero)")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/ledger_analysis_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "backtest/ledger_run2.csv.gz")
