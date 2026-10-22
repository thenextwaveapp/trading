#!/usr/bin/env python3
"""Phase 3, step 1: cluster trades by the SHAPE of their forward price path.

For each trade: direction-adjusted cumulative return at fixed offsets after entry
(15m grid to 4h), normalized by the coin's own volatility (ATR) so shapes are
comparable across BTC and memecoins. K-means over the paths; then profile each
cluster: size, outcome, entry conditions, traders, coins.

Usage: python3 cluster_paths.py [k]
Writes: reports/path_clusters_<stamp>.txt
"""
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from build_feature_matrix import read_partial_gz_csv, scale_for

GRID_MIN = [15, 30, 45, 60, 90, 120, 180, 240]  # minutes after entry
OUT = []


def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def main(k=6):
    m = pd.read_csv("master/feature_matrix.csv")
    m = m[(m["price_mismatch"] == 0) & m["y_fwd_ret_4h"].notna() & m["f_natr_24h"].notna()].copy()
    c15 = read_partial_gz_csv("bn/bn_candles_15m.csv.gz")
    c1 = read_partial_gz_csv("bn/bn_candles_1h.csv.gz")
    M15, H = 900_000, 3_600_000

    series = {}
    for tk, g in c15.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t")
        series[tk] = [g["t"].to_numpy("int64"), g["c"].to_numpy(float)]
    series1 = {}
    for tk, g in c1.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t")
        series1[tk] = [g["t"].to_numpy("int64"), g["c"].to_numpy(float)]

    def price_at(tk, target):
        d = series.get(tk)
        if d is not None:
            i = np.searchsorted(d[0], target, "right") - 1
            if i >= 0 and target < d[0][i] + M15:
                return d[1][i]
        d = series1.get(tk)
        if d is not None:
            i = np.searchsorted(d[0], target, "right") - 1
            if i >= 0 and target < d[0][i] + H:
                return d[1][i]
        return None

    paths, keep_idx, pre_moves = [], [], []
    for tr in m.itertuples():
        s = 1 if tr.side == "long" else -1
        entry = float(tr.entry_price) * scale_for(tr.ticker, tr.symbol)
        path = []
        for mins in GRID_MIN:
            px = price_at(tr.ticker, tr.t0_ms + mins * 60_000)
            if px is None:
                break
            path.append(s * (px / entry - 1))
        if len(path) < len(GRID_MIN):
            continue
        # pre-entry micro-move (same-candle open -> fill), for profiling
        d = series.get(tr.ticker)
        pre = np.nan
        if d is not None:
            i = np.searchsorted(d[0], tr.t0_ms, "right") - 1
            if i >= 0 and tr.t0_ms < d[0][i] + M15:
                # use candle open: approximate with previous close
                if i > 0:
                    pre = s * (entry / d[1][i - 1] - 1)
        paths.append(path)
        pre_moves.append(pre)
        keep_idx.append(tr.Index)

    X = np.array(paths)
    mm = m.loc[keep_idx].copy()
    mm["pre_move"] = pre_moves
    natr = mm["f_natr_24h"].to_numpy()[:, None]
    Xn = X / natr  # vol-normalized shapes
    Xn = np.clip(Xn, -5, 5)  # cap monster outliers so k-means sees shape, not one moonshot

    km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(Xn)
    mm["cluster"] = km.labels_

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FORWARD PATH CLUSTERING — {stamp}")
    p(f"trades with full 4h paths: {len(mm):,} | grid: {GRID_MIN} min | k={k}")
    p("paths are direction-adjusted, ATR-normalized; profiling in raw % below")
    p("")

    order = mm.groupby("cluster")["y_fwd_ret_4h"].mean().sort_values(ascending=False).index
    for rank, cl in enumerate(order, 1):
        g = mm[mm["cluster"] == cl]
        gx = X[mm["cluster"].to_numpy() == cl]
        mean_path = gx.mean(0) * 100
        med_path = np.median(gx, 0) * 100
        p("=" * 78)
        p(f"CLUSTER {rank}  (n={len(g):,}, {len(g)/len(mm)*100:.0f}% of trades)")
        p(f"  mean path   % : " + "  ".join(f"{v:+6.2f}" for v in mean_path))
        p(f"  median path % : " + "  ".join(f"{v:+6.2f}" for v in med_path))
        p(f"                  " + "  ".join(f"{g_:>6}" for g_ in ["15m", "30m", "45m", "1h", "90m", "2h", "3h", "4h"]))
        p(f"  outcomes: 4h {g['y_fwd_ret_4h'].mean()*100:+.2f}% (hit {(g['y_fwd_ret_4h']>0).mean()*100:.0f}%) | "
          f"24h {g['y_fwd_ret_24h'].mean()*100:+.2f}% | MAE24 med {g['y_mae_24h'].median()*100:.2f}%")
        p(f"  entry state: pre-move {g['pre_move'].median()*100:+.2f}% | vol_z {g['f_vol_z_1h'].median():+.2f} | "
          f"natr {g['f_natr_24h'].median()*100:.1f}% | ret_24h {g['f_ret_24h'].median()*100:+.1f}% | "
          f"range-pos {g['f_range_pos_24h'].median():.2f}")
        p(f"  mix: long {(g['side']=='long').mean()*100:.0f}% | majors {(g['ticker'].isin({'BTC','ETH','SOL','XRP','BNB','DOGE','ADA','LINK','AVAX','LTC'})).mean()*100:.0f}% | "
          f"lev med {g['f_leverage'].median():.0f}x")
        top_u = g["username"].value_counts(normalize=True).head(3)
        top_t = g["ticker"].value_counts(normalize=True).head(3)
        p(f"  top traders: " + ", ".join(f"{u} {v*100:.0f}%" for u, v in top_u.items())
          + " | top coins: " + ", ".join(f"{t} {v*100:.0f}%" for t, v in top_t.items()))

    p("")
    p("=" * 78)
    p("THEIR EXITS vs THE MARKET PATH (what the humans actually banked, unleveraged)")
    mm["realized_unlev"] = pd.to_numeric(mm["invo_return_pct"], errors="coerce") / mm["f_leverage"] / 100
    ex = mm[mm["realized_unlev"].abs() < 1]
    p(f"  {'cluster':<10}{'n':>7}{'market@4h':>11}{'their exit':>12}{'hold med':>10}{'their win%':>11}")
    for rank, cl in enumerate(order, 1):
        g = ex[ex["cluster"] == cl]
        hold = pd.to_numeric(g["invo_hold_s"], errors="coerce").median() / 3600
        p(f"  C{rank:<9}{len(g):7,}{g['y_fwd_ret_4h'].mean()*100:>+10.2f}%{g['realized_unlev'].mean()*100:>+11.2f}%"
          f"{hold:>9.1f}h{(g['realized_unlev']>0).mean()*100:>10.0f}%")
    p("  -> their exits: poor at harvesting winners, excellent at damage control.")
    p("     Fixed-horizon returns understate entry+smart-exit, overstate entry+dumb-exit.")

    p("")
    p("Sanity: cluster sizes " + str(sorted(np.bincount(km.labels_), reverse=True)))
    import os
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/path_clusters_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
