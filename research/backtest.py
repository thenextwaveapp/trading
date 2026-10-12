#!/usr/bin/env python3
"""Phase 4: STANDALONE backtest — no traders involved.

Scan every 15m candle close in the test window for all universe tickers, both
directions. Compute the same live-computable features as the matrix, score with
a model trained ONLY on trader entries BEFORE the test window, enter when the
score clears a threshold calibrated on pre-test scan data, hold 4h, exit.

Timeline:
  warmup      2026-07-15 .. 2026-07-31   (feature lookback only)
  calibrate   2026-08-01 .. 2026-08-18   (threshold = top X% of scanned scores)
  TEST        2026-08-19 .. 2026-10-03   (out-of-time, same cutoff as classifier)

Cost scenarios per round trip (fees + slippage):
  optimistic  0.04%  (maker both sides + minimal impact)
  base        0.17%  (taker both sides 0.07% + 0.05% slip each side)
  harsh       0.47%  (taker + 0.2% slip each side — thin alt books)

Writes: reports/backtest_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

M15 = 900_000
H = 3_600_000
CUT_TEST = pd.Timestamp("2026-08-19", tz="UTC").value // 10**6
CUT_CAL = pd.Timestamp("2026-08-01", tz="UTC").value // 10**6
SIGNAL_PCT = 99.0          # fire on top 1% of scanned scores (calibrated pre-test)
HOLD = 16                  # 15m candles = 4h
COSTS = {"optimistic": 0.0004, "base": 0.0017, "harsh": 0.0047}

MARKET_FEATS = [
    "f_ret_1h", "f_ret_4h", "f_ret_24h", "f_dist_high_24h", "f_dist_low_24h",
    "f_range_pos_24h", "f_ema20_dev", "f_ema50_dev", "f_atr_ratio_6_24",
    "f_natr_24h", "f_bb_bw_20", "f_park_vol_24h", "f_park_pctl_30d",
    "f_vol_z_1h", "f_taker_buy_ratio", "f_fund_rate", "f_fund_vel",
    "f_fund_pctl_7d", "f_side_sign", "f_hour_utc", "f_dow",
    "f_pre15", "f_pre30", "f_pre60", "f_pre_hi1h", "f_pre_lo1h", "f_vol15_ratio",
]

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def hourly_features(g):
    """Vectorized 1h-candle features, valid AS OF each candle's close."""
    c, h, l, v, tb = g["c"], g["h"], g["l"], g["v"], g["taker_buy_v"]
    f = pd.DataFrame(index=g.index)
    f["close_t"] = g["t"] + H  # feature row becomes visible at candle close
    f["f_ret_1h"] = c.pct_change(1)
    f["f_ret_4h"] = c.pct_change(4)
    f["f_ret_24h"] = c.pct_change(24)
    hi24, lo24 = h.rolling(24).max(), l.rolling(24).min()
    f["f_dist_high_24h"] = c / hi24 - 1
    f["f_dist_low_24h"] = c / lo24 - 1
    f["f_range_pos_24h"] = (c - lo24) / (hi24 - lo24)
    f["f_ema20_dev"] = c / c.ewm(span=20, adjust=False).mean() - 1
    f["f_ema50_dev"] = c / c.ewm(span=50, adjust=False).mean() - 1
    prev_c = c.shift(1)
    tr = np.maximum(h, prev_c) - np.minimum(l, prev_c)
    atr6, atr24 = tr.rolling(6).mean(), tr.rolling(24).mean()
    f["f_atr_ratio_6_24"] = atr6 / atr24
    f["f_natr_24h"] = atr24 / c
    sma20, std20 = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    f["f_bb_bw_20"] = 4 * std20 / sma20
    park = (np.log(h / l) ** 2 / (4 * np.log(2))).rolling(24).mean() ** 0.5
    f["f_park_vol_24h"] = park
    f["f_park_pctl_30d"] = park.rolling(720, min_periods=100).rank(pct=True) * 100
    vmu = v.shift(1).rolling(24).mean()
    vsd = v.shift(1).rolling(24).std(ddof=0)
    f["f_vol_z_1h"] = (v - vmu) / vsd
    f["f_taker_buy_ratio"] = tb / v
    for col in ("f_fund_rate", "f_fund_vel", "f_fund_pctl_7d"):
        f[col] = np.nan  # not fetched for scan; model handles missing
    return f


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- model: train on trader entries strictly before the test window ----
    m = pd.read_csv("master/feature_matrix.csv")
    m = m[(m["price_mismatch"] == 0) & m["y_fwd_ret_4h"].notna()].copy()
    tr = m[m["t0_ms"] < CUT_TEST]
    feats = [f for f in MARKET_FEATS if f in tr.columns]
    clf = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
        validation_fraction=0.15, early_stopping=True, random_state=7)
    clf.fit(tr[feats], (tr["y_fwd_ret_4h"] > 0.0025).astype(int))

    # ---- scan grid ----
    c15 = pd.read_csv("backtest/bt_candles_15m.csv.gz")
    c1 = pd.read_csv("backtest/bt_candles_1h.csv.gz")
    rows = []
    for tk, g15 in c15.groupby("ticker"):
        g15 = g15.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        g1 = c1[c1["ticker"] == tk].drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if len(g1) < 60 or len(g15) < 200:
            continue
        hf = hourly_features(g1)

        c = g15["c"].to_numpy(float)
        hh = g15["h"].to_numpy(float)
        ll = g15["l"].to_numpy(float)
        vv = g15["v"].to_numpy(float)
        t = g15["t"].to_numpy(np.int64)
        n = len(g15)

        # fast features at each decision point i (candle i closed; price = c[i];
        # history windows exclude candle i to mirror matrix construction)
        pre15 = np.full(n, np.nan); pre30 = np.full(n, np.nan); pre60 = np.full(n, np.nan)
        prehi = np.full(n, np.nan); prelo = np.full(n, np.nan); vrat = np.full(n, np.nan)
        for i in range(9, n):
            if t[i] - t[i - 1] != M15:
                continue
            pre15[i] = c[i] / c[i - 1] - 1
            pre30[i] = c[i] / c[i - 2] - 1
            pre60[i] = c[i] / c[i - 4] - 1
            prehi[i] = c[i] / hh[i - 4:i].max() - 1
            prelo[i] = c[i] / ll[i - 4:i].min() - 1
            mu = vv[i - 8:i].mean()
            vrat[i] = vv[i] / mu if mu > 0 else np.nan

        grid = pd.DataFrame({
            "ticker": tk, "t_dec": t + M15, "i": np.arange(n), "price": c,
            "raw_pre15": pre15, "raw_pre30": pre30, "raw_pre60": pre60,
            "raw_prehi": prehi, "raw_prelo": prelo, "f_vol15_ratio": vrat,
        })
        # attach last CLOSED 1h feature row
        hf = hf.sort_values("close_t")
        grid = pd.merge_asof(grid.sort_values("t_dec"), hf, left_on="t_dec",
                             right_on="close_t", direction="backward")
        # forward exit price (hold 4h) — next-candle entry assumed at c[i] (decision price)
        exit_px = np.full(n, np.nan)
        ok = (np.arange(n) + HOLD < n) & (t + HOLD * M15 == np.concatenate([t[HOLD:], np.full(HOLD, -1)]))
        exit_px[ok[:n]] = c[np.arange(n)[ok] + HOLD]
        grid["exit_px"] = exit_px
        rows.append(grid)

    grid = pd.concat(rows, ignore_index=True)
    grid = grid.dropna(subset=["raw_pre15", "exit_px", "f_ret_24h"])
    dt = pd.to_datetime(grid["t_dec"], unit="ms", utc=True)
    grid["f_hour_utc"] = dt.dt.hour
    grid["f_dow"] = dt.dt.dayofweek

    # score both sides
    scans = []
    for side in (1, -1):
        gs = grid.copy()
        gs["f_side_sign"] = side
        for raw, feat in [("raw_pre15", "f_pre15"), ("raw_pre30", "f_pre30"),
                          ("raw_pre60", "f_pre60"),
                          ("raw_prehi", "f_pre_hi1h"), ("raw_prelo", "f_pre_lo1h")]:
            gs[feat] = side * gs[raw]
        gs["score"] = clf.predict_proba(gs[feats])[:, 1]
        gs["fwd"] = side * (gs["exit_px"] / gs["price"] - 1)
        scans.append(gs[["ticker", "t_dec", "f_side_sign", "score", "fwd", "price"]])
    scan = pd.concat(scans, ignore_index=True)

    cal = scan[(scan["t_dec"] >= CUT_CAL) & (scan["t_dec"] < CUT_TEST)]
    test = scan[scan["t_dec"] >= CUT_TEST]
    thresh = np.percentile(cal["score"], SIGNAL_PCT)

    p(f"STANDALONE BACKTEST — {stamp}")
    p(f"universe: {grid['ticker'].nunique()} tickers | scan points (both sides): "
      f"cal {len(cal):,}, test {len(test):,}")
    p(f"model: trained on {len(tr):,} trader entries < 2026-08-19 (market features only)")
    p(f"threshold: score >= {thresh:.3f} (= top {100-SIGNAL_PCT:.0f}% of calibration scans, pre-test)")
    p(f"hold: 4h | one position per ticker at a time | equal weight per trade")
    p("")

    sig = test[test["score"] >= thresh].sort_values("t_dec")
    # one open position per ticker
    taken, busy = [], {}
    for r in sig.itertuples():
        if busy.get(r.ticker, 0) <= r.t_dec:
            taken.append(r)
            busy[r.ticker] = r.t_dec + HOLD * M15
    tk_df = pd.DataFrame([{"ticker": r.ticker, "t": r.t_dec, "side": r.f_side_sign,
                           "score": r.score, "fwd": r.fwd} for r in taken])

    p("=" * 78)
    p(f"RESULTS — TEST WINDOW 2026-08-19 .. 2026-10-03 ({(test['t_dec'].max()-test['t_dec'].min())/86400000:.0f} days)")
    p(f"signals fired: {len(sig):,} | trades after one-per-ticker cap: {len(tk_df):,} "
      f"(~{len(tk_df)/45:.1f}/day)")
    if not len(tk_df):
        p("NO TRADES — threshold never hit in test window.")
    else:
        gross = tk_df["fwd"]
        p(f"\ngross per trade: mean {gross.mean()*100:+.3f}%  median {gross.median()*100:+.3f}%  "
          f"hit {(gross>0).mean()*100:.1f}%")
        p(f"\n{'scenario':<12}{'cost/rt':>9}{'net/trade':>11}{'total':>9}{'hit':>7}{'maxDD':>8}")
        for nm, cost in COSTS.items():
            net = gross - cost
            eq = net.cumsum()
            dd = (eq - eq.cummax()).min()
            p(f"{nm:<12}{cost*100:>8.2f}%{net.mean()*100:>+10.3f}%{net.sum()*100:>+8.1f}%"
              f"{(net>0).mean()*100:>6.1f}%{dd*100:>7.1f}%")
        p("\nby side: " + " | ".join(
            f"{'long' if s>0 else 'short'}: n={len(g)}, gross {g['fwd'].mean()*100:+.3f}%"
            for s, g in tk_df.groupby("side")))
        p("\nby ticker (gross):")
        bt = tk_df.groupby("ticker")["fwd"].agg(["size", "mean", "sum"]).sort_values("sum", ascending=False)
        for tkr, r in bt.iterrows():
            p(f"  {tkr:10} n={int(r['size']):4}  mean {r['mean']*100:+.3f}%  total {r['sum']*100:+.2f}%")
        wk = tk_df.copy()
        wk["week"] = pd.to_datetime(wk["t"], unit="ms").dt.strftime("%Y-%U")
        p("\nby week (gross sum): " + "  ".join(
            f"{w}:{g['fwd'].sum()*100:+.1f}%" for w, g in wk.groupby("week")))

    # context: what would random scan moments have done (base drift check)
    p("")
    p(f"context — ALL test scan points (both sides, no model): gross mean "
      f"{test['fwd'].mean()*100:+.4f}% (should be ~0)")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
