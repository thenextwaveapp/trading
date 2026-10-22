#!/usr/bin/env python3
"""Phase 3 gate: can entry-time features predict trade outcome, out-of-time?

Chronological split (no future leakage). Two feature sets:
  MARKET-ONLY     — what a standalone bot sees (candles/funding/time/side)
  + TRADER-CONTEXT — adds leverage & cohort features (requires watching Invo live)

Target: y_fwd_ret_4h > 0.25% (clears taker fees + slippage headroom).
Scores: ROC-AUC + quintile lift on the held-out future (the economic read).

Writes: reports/classifier_test_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

MARKET_FEATS = [
    "f_ret_1h", "f_ret_4h", "f_ret_24h", "f_dist_high_24h", "f_dist_low_24h",
    "f_range_pos_24h", "f_ema20_dev", "f_ema50_dev", "f_atr_ratio_6_24",
    "f_natr_24h", "f_bb_bw_20", "f_park_vol_24h", "f_park_pctl_30d",
    "f_vol_z_1h", "f_taker_buy_ratio", "f_fund_rate", "f_fund_vel",
    "f_fund_pctl_7d", "f_side_sign", "f_hour_utc", "f_dow",
    # fast intra-hour features (live-computable: recent 15m candles + current price)
    "f_pre15", "f_pre30", "f_pre60", "f_pre_hi1h", "f_pre_lo1h", "f_vol15_ratio",
]
TRADER_FEATS = MARKET_FEATS + [
    "f_leverage", "f_cohort_n_1h", "f_cohort_n_4h", "f_cohort_n_24h",
    "f_cohort_traders_1h", "f_cohort_traders_4h", "f_cohort_traders_24h",
    "f_cohort_sameside_4h",
]
THRESH = 0.0025  # 4h fwd return must clear 0.25%

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def run(m, feats, label):
    m = m.sort_values("t0_ms").reset_index(drop=True)
    cut = int(len(m) * 0.7)
    tr, te = m.iloc[:cut], m.iloc[cut:]
    Xtr, ytr = tr[feats], (tr["y_fwd_ret_4h"] > THRESH).astype(int)
    Xte, yte = te[feats], (te["y_fwd_ret_4h"] > THRESH).astype(int)

    clf = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
        validation_fraction=0.15, early_stopping=True, random_state=7)
    clf.fit(Xtr, ytr)
    prob = clf.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, prob)

    p("")
    p("=" * 78)
    p(f"{label}")
    p(f"  train: {len(tr):,} trades ({tr['opened_at'].min()[:10]} -> {tr['opened_at'].max()[:10]})")
    p(f"  test:  {len(te):,} trades ({te['opened_at'].min()[:10]} -> {te['opened_at'].max()[:10]})  "
      f"base rate {yte.mean()*100:.1f}%")
    p(f"  ROC-AUC (out-of-time): {auc:.3f}   (0.500 = no signal)")
    p(f"  Economic read — test trades bucketed by model score:")
    te2 = te.copy()
    te2["prob"] = prob
    te2["q"] = pd.qcut(te2["prob"], 5, labels=["Q1 worst", "Q2", "Q3", "Q4", "Q5 best"])
    p(f"    {'bucket':<10}{'n':>7}{'mean 4h fwd':>13}{'hit>0':>8}{'hit>fees':>9}")
    for q, g in te2.groupby("q", observed=True):
        r = g["y_fwd_ret_4h"] * 100
        p(f"    {str(q):<10}{len(g):7,}{r.mean():>+12.3f}%{(r>0).mean()*100:>7.1f}%{(r>0.25).mean()*100:>8.1f}%")
    top, bot = te2[te2["q"] == "Q5 best"], te2[te2["q"] == "Q1 worst"]
    spread = (top["y_fwd_ret_4h"].mean() - bot["y_fwd_ret_4h"].mean()) * 100
    p(f"  Q5-Q1 spread: {spread:+.3f}% per trade | Q5 alone: {top['y_fwd_ret_4h'].mean()*100:+.3f}% "
      f"vs all-trades {te2['y_fwd_ret_4h'].mean()*100:+.3f}%")
    return te2, clf


def main():
    m = pd.read_csv("master/feature_matrix.csv")
    m = m[(m["price_mismatch"] == 0) & m["y_fwd_ret_4h"].notna()].copy()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"OUT-OF-TIME CLASSIFIER TEST — {stamp}")
    p(f"rows: {len(m):,} | target: 4h fwd return > {THRESH*100:.2f}% | split: first 70% train, last 30% test")
    p("CAVEAT: all rows are trader-selected moments. This tests ranking AMONG their")
    p("entries. Whether the same conditions fire standalone is the backtest's question.")

    te_mkt, _ = run(m, [f for f in MARKET_FEATS if f in m.columns], "MARKET-ONLY FEATURES (standalone bot)")
    te_all, clf = run(m, [f for f in TRADER_FEATS if f in m.columns], "MARKET + TRADER-CONTEXT FEATURES")

    # permutation importance on the full model, test set (which signals carry it)
    from sklearn.inspection import permutation_importance
    feats = [f for f in TRADER_FEATS if f in m.columns]
    msort = m.sort_values("t0_ms").reset_index(drop=True)
    cut = int(len(msort) * 0.7)
    te = msort.iloc[cut:]
    r = permutation_importance(clf, te[feats], (te["y_fwd_ret_4h"] > THRESH).astype(int),
                               n_repeats=3, random_state=7, scoring="roc_auc")
    p("")
    p("=" * 78)
    p("TOP FEATURES (permutation importance on held-out test, AUC drop)")
    idx = np.argsort(-r.importances_mean)[:12]
    for i in idx:
        p(f"  {feats[i]:<24} {r.importances_mean[i]:+.4f}")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/classifier_test_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
