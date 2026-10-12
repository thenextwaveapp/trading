#!/usr/bin/env python3
"""Mine the actual Invo trader dataset for the LONG edge.

Not a candle-rule guess — this asks the data directly:
  1. WHO: which traders actually make money on longs (fwd returns at entry,
     not their illusory paper return_pct), and is it persistent?
  2. WHEN: what market conditions (f_* features) separate winning long
     entries from losing ones — quintile sweep over every feature.
  3. SHAPE: entry anatomy of the successful cohort (dip vs chase, vol,
     funding, range position, cohort crowding).
  4. EXIT: what the winners' holds/exits look like vs MFE/MAE — what hold
     horizon the long edge actually wants.
  5. RULE DRAFT: conditions from the top features' winning ranges, measured
     jointly, with params read off the winners' distribution.

Usage: python3 long_miner.py
Writes: reports/long_miner_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


HZ = [("30m", "y_fwd_ret_30m"), ("1h", "y_fwd_ret_1h"), ("4h", "y_fwd_ret_4h"),
      ("8h", "y_fwd_ret_8h"), ("24h", "y_fwd_ret_24h"), ("48h", "y_fwd_ret_48h")]

FEATS = ["f_ret_1h", "f_ret_4h", "f_ret_24h", "f_dist_high_24h",
         "f_dist_low_24h", "f_range_pos_24h", "f_ema20_dev", "f_ema50_dev",
         "f_atr_ratio_6_24", "f_natr_24h", "f_bb_bw_20", "f_park_vol_24h",
         "f_park_pctl_30d", "f_vol_z_1h", "f_taker_buy_ratio", "f_fund_rate",
         "f_fund_vel", "f_fund_pctl_7d", "f_pre15", "f_pre30", "f_pre60",
         "f_pre_hi1h", "f_pre_lo1h", "f_vol15_ratio", "f_leverage",
         "f_cohort_n_4h", "f_cohort_sameside_4h"]


def hline(label, g, col="y_fwd_ret_4h"):
    if len(g) < 20:
        p(f"  {label:42s} n={len(g):5,}  (too few)")
        return
    parts = " ".join(f"{h}:{g[c].mean()*100:+.2f}" for h, c in HZ)
    p(f"  {label:42s} n={len(g):5,}  {parts}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"INVO LONG-SIDE MINER — {stamp}")
    f = pd.read_csv("master/feature_matrix.csv")
    dead = pd.read_csv("master/dead_flags.csv")
    f = f.merge(dead, on="trade_id", how="left")
    f = f[f["dead"] != True]
    L = f[(f["side"] == "long") & f["y_fwd_ret_4h"].notna()].copy()
    S = f[(f["side"] == "short") & f["y_fwd_ret_4h"].notna()].copy()
    L["year"] = pd.to_datetime(L["opened_at"]).dt.year
    p(f"clean rows: {len(f):,} | longs with outcomes: {len(L):,} | "
      f"shorts: {len(S):,}")

    # ---------------------------------------------------------------- 1. WHO
    p("")
    p("=" * 110)
    p("1. WHO — per-trader LONG performance (market-measured fwd returns, "
      "not Invo paper return_pct)")
    p(f"{'trader':16s} {'n':>5s} {'4h':>7s} {'24h':>7s} {'48h':>7s} "
      f"{'hit4h':>6s} {'medhold':>8s} {'invo%':>8s}")
    rows = []
    for tr, g in L.groupby("username"):
        if len(g) < 30:
            continue
        rows.append(dict(trader=tr, n=len(g),
                         r4=g["y_fwd_ret_4h"].mean(),
                         r24=g["y_fwd_ret_24h"].mean(),
                         r48=g["y_fwd_ret_48h"].mean(),
                         hit=(g["y_fwd_ret_4h"] > 0).mean(),
                         hold=g["invo_hold_s"].median() / 3600,
                         invo=g["invo_return_pct"].mean()))
    tt = pd.DataFrame(rows).sort_values("r4", ascending=False)
    for _, r in tt.iterrows():
        p(f"{r['trader']:16s} {r['n']:5,} {r['r4']*100:+6.2f}% "
          f"{r['r24']*100:+6.2f}% {r['r48']*100:+6.2f}% {r['hit']*100:5.0f}% "
          f"{r['hold']:7.1f}h {r['invo']:+7.1f}%")
    top_traders = set(tt.head(10)["trader"])
    p(f"\nlong-skilled cohort (top 10 by 4h fwd): {sorted(top_traders)}")
    LT = L[L["username"].isin(top_traders)]
    hline("ALL longs", L)
    hline("long-skilled cohort", LT)

    # persistence: split each trader's longs into halves by time
    p("")
    p("persistence (per-trader first-half vs second-half 4h fwd, n>=40):")
    pers = []
    for tr, g in L.groupby("username"):
        if len(g) < 40:
            continue
        g = g.sort_values("t0_ms")
        a = g.head(len(g) // 2)["y_fwd_ret_4h"].mean()
        b = g.tail(len(g) // 2)["y_fwd_ret_4h"].mean()
        pers.append((tr, a, b))
    pe = pd.DataFrame(pers, columns=["tr", "h1", "h2"])
    same = ((pe["h1"] > 0) == (pe["h2"] > 0)).mean()
    p(f"  {len(pe)} traders | rank-corr h1 vs h2: "
      f"{pe['h1'].corr(pe['h2'], method='spearman'):+.2f} | same-sign "
      f"{same*100:.0f}% | both-positive "
      f"{((pe['h1'] > 0) & (pe['h2'] > 0)).mean()*100:.0f}%")

    # ---------------------------------------------------- 2. WHEN (features)
    p("")
    p("=" * 110)
    p("2. WHEN — feature quintile sweep on ALL longs: mean 4h fwd by "
      "quintile, spread = Q5-Q1")
    p(f"{'feature':22s} {'Q1':>7s} {'Q2':>7s} {'Q3':>7s} {'Q4':>7s} "
      f"{'Q5':>7s} {'spread':>8s}  (and 24h spread)")
    sweeps = []
    for ft in FEATS:
        g = L[L[ft].notna()]
        if len(g) < 500:
            continue
        try:
            q = pd.qcut(g[ft], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        m4 = g.groupby(q)["y_fwd_ret_4h"].mean()
        m24 = g.groupby(q)["y_fwd_ret_24h"].mean()
        if len(m4) < 5:
            continue
        sp4, sp24 = m4.iloc[4] - m4.iloc[0], m24.iloc[4] - m24.iloc[0]
        sweeps.append((ft, abs(sp4), sp4, sp24, m4))
    sweeps.sort(key=lambda x: -x[1])
    for ft, _, sp4, sp24, m4 in sweeps:
        p(f"{ft:22s} " + " ".join(f"{v*100:+6.2f}" for v in m4.values)
          + f" {sp4*100:+7.2f}%  ({sp24*100:+.2f}%)")

    # ------------------------------------------------------- 3. ENTRY SHAPE
    p("")
    p("=" * 110)
    p("3. ENTRY SHAPE — successful vs failed longs (4h fwd > +1% vs < -1%), "
      "median feature values")
    win = L[L["y_fwd_ret_4h"] > 0.01]
    lose = L[L["y_fwd_ret_4h"] < -0.01]
    p(f"{'feature':22s} {'winners':>10s} {'losers':>10s} {'all-longs':>10s}")
    for ft in FEATS:
        p(f"{ft:22s} {win[ft].median():10.4f} {lose[ft].median():10.4f} "
          f"{L[ft].median():10.4f}")

    # --------------------------------------------------------------- 4. EXIT
    p("")
    p("=" * 110)
    p("4. EXIT — hold horizon and capture, longs only")
    L["hold_h"] = L["invo_hold_s"] / 3600
    for lo, hi, lab in [(0, 1, "<1h"), (1, 4, "1-4h"), (4, 24, "4-24h"),
                        (24, 24 * 7, "1-7d"), (24 * 7, 1e9, ">7d")]:
        g = L[(L["hold_h"] >= lo) & (L["hold_h"] < hi)]
        hline(f"hold {lab}", g)
    p("")
    cap = L[(L["y_mfe_24h"].notna()) & (L["y_mfe_24h"] > 0)]
    p(f"MFE capture (longs, 24h): median MFE {cap['y_mfe_24h'].median()*100:+.2f}% "
      f"| median MAE {L['y_mae_24h'].median()*100:+.2f}% "
      f"| invo realized median {L['invo_return_pct'].median():+.2f}%")
    p("fwd return curve, ALL longs vs skilled cohort (is the edge "
      "front-loaded or drift?):")
    hline("ALL longs", L)
    hline("skilled cohort", LT)

    # ------------------------------------------------- 5. RULE DRAFT (joint)
    p("")
    p("=" * 110)
    p("5. JOINT CONDITIONS — stack the top discriminating features, "
      "read params off winners")
    # conditions tested are set AFTER seeing section 2/3 output in a second
    # pass; first pass prints the building blocks below for honesty.
    combos = [
        ("dip entry: f_pre_lo1h <= -2%", L["f_pre_lo1h"] <= -0.02),
        ("dip entry: f_pre_lo1h <= -4%", L["f_pre_lo1h"] <= -0.04),
        ("dump day: f_ret_24h <= -10%", L["f_ret_24h"] <= -0.10),
        ("dump 4h: f_ret_4h <= -5%", L["f_ret_4h"] <= -0.05),
        ("low in range: f_range_pos_24h <= 0.3", L["f_range_pos_24h"] <= 0.3),
        ("high vol: f_natr_24h top half", L["f_natr_24h"] >= L["f_natr_24h"].median()),
        ("vol spike: f_vol15_ratio >= 2", L["f_vol15_ratio"] >= 2),
        ("neg funding: f_fund_rate < 0", L["f_fund_rate"] < 0),
        ("low leverage <= 3", L["f_leverage"] <= 3),
        ("uncrowded: cohort_n_4h <= 2", L["f_cohort_n_4h"] <= 2),
        ("dip + dump day", (L["f_pre_lo1h"] <= -0.02) & (L["f_ret_24h"] <= -0.10)),
        ("dip + low range + high vol",
         (L["f_pre_lo1h"] <= -0.02) & (L["f_range_pos_24h"] <= 0.3)
         & (L["f_natr_24h"] >= L["f_natr_24h"].median())),
        ("dip + neg funding", (L["f_pre_lo1h"] <= -0.02) & (L["f_fund_rate"] < 0)),
        ("dump day + neg funding",
         (L["f_ret_24h"] <= -0.10) & (L["f_fund_rate"] < 0)),
    ]
    p(f"  {'condition':42s} {'n':>6s}  fwd means (gross %)")
    hline("ALL longs (ref)", L)
    for lab, mask in combos:
        hline(lab, L[mask])

    p("")
    p("same combos, SKILLED COHORT only:")
    for lab, mask in combos[:6]:
        hline(lab, LT[mask.reindex(LT.index)])

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/long_miner_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f_:
        f_.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
