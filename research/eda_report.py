#!/usr/bin/env python3
"""Full EDA report for the Invo trades dataset + (if present) the feature matrix.

Usage: python3 eda_report.py
Writes: reports/eda_report_<UTCstamp>.txt (and echoes to stdout)

Re-run any time (e.g. after the Binance pull completes or a new scrape) to
regenerate the report on current data.
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

TRADES = "master/invo_trades_master.csv"
MATRIX = "master/feature_matrix.csv"
COVERAGE = "bn/bn_coverage.csv"

OUT = []
def p(*args):
    line = " ".join(str(a) for a in args)
    OUT.append(line)
    print(line)

def load_btc_daily():
    """Daily BTC closes from the pulled 1h candles (partial-gzip tolerant)."""
    import gzip, io
    path = "bn/bn_candles_1h.csv.gz"
    if not os.path.exists(path):
        return None
    buf = io.BytesIO()
    try:
        with gzip.open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                buf.write(chunk)
    except (EOFError, OSError):
        pass
    raw = buf.getvalue()
    last_nl = raw.rfind(b"\n")
    if last_nl < 0:
        return None
    c = pd.read_csv(io.BytesIO(raw[: last_nl + 1]))
    c = c[c["ticker"] == "BTC"]
    if not len(c):
        return None
    c["date"] = pd.to_datetime(c["t"], unit="ms").dt.normalize()
    return c.groupby("date")["c"].last()


def hdr(title):
    p("")
    p("=" * 78)
    p(f"  {title}")
    p("=" * 78)

def sub(title):
    p("")
    p(f"--- {title} ---")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    df = pd.read_csv(TRADES)
    df["t0"] = pd.to_datetime(df["opened_at"], format="ISO8601")
    df["hour_utc"] = df["t0"].dt.hour
    df["dow"] = df["t0"].dt.dayofweek
    closed = df[df["status"] == "closed"].copy()

    p(f"INVO TRADER DATASET — EXPLORATORY DATA ANALYSIS REPORT")
    p(f"Generated: {stamp}")
    p(f"Source: {TRADES}")

    # ------------------------------------------------------------------
    hdr("0. DATASET OVERVIEW")
    p(f"Total unique trades:   {len(df):,}")
    p(f"  closed: {len(closed):,}   open: {(df['status']=='open').sum():,}")
    p(f"Unique traders:        {df['username'].nunique()}")
    p(f"Unique tickers:        {df['ticker'].nunique()}")
    p(f"Entry date range:      {df['t0'].min():%Y-%m-%d} -> {df['t0'].max():%Y-%m-%d}")
    sub("Trades per month")
    bym = df.groupby(df["t0"].dt.strftime("%Y-%m")).size()
    mx = bym.max()
    for m, n in bym.items():
        p(f"  {m}  {n:5,}  {'#' * int(40 * n / mx)}")

    # ------------------------------------------------------------------
    hdr("1. TEMPORAL & SESSION CLUSTERING")
    sub("Entries by UTC hour")
    byh = df.groupby("hour_utc").size()
    mx = byh.max()
    for h, n in byh.items():
        tag = ""
        if h == 0: tag = "  <- Asia open"
        if h == 8: tag = "  <- EU open"
        if h in (13, 14): tag = "  <- US equity open 13:30"
        p(f"  {h:02d}:00  {n:5,}  {'#' * int(40 * n / mx)}{tag}")
    sub("Entries by day of week")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    byd = df.groupby("dow").size()
    for d, n in byd.items():
        p(f"  {days[d]}  {n:5,}  {'#' * int(40 * n / byd.max())}")
    sub("Hour x Day heatmap (trade counts)")
    hm = df.pivot_table(index="hour_utc", columns="dow", values="trade_id", aggfunc="count").fillna(0).astype(int)
    p("  hour | " + "  ".join(f"{days[c]:>4}" for c in hm.columns))
    for h, row in hm.iterrows():
        p(f"  {h:02d}   | " + "  ".join(f"{v:4d}" for v in row))

    # ------------------------------------------------------------------
    hdr("2. CONCENTRATION & PARETO")
    tc = df["username"].value_counts()
    lorenz = tc.sort_values().cumsum() / tc.sum()
    gini = 1 - 2 * np.trapezoid(np.append(0, lorenz), dx=1 / len(tc))
    p(f"Trader Gini coefficient: {gini:.2f}")
    cum = tc.cumsum() / len(df) * 100
    p(f"Top 5 traders:  {cum.iloc[4]:.0f}% of all trades")
    p(f"Top 10 traders: {cum.iloc[9]:.0f}% of all trades")
    p(f"Top 20 traders: {cum.iloc[19]:.0f}% of all trades")
    kc = df["ticker"].value_counts()
    p(f"\nTop 20 tickers = {kc.head(20).sum()/len(df)*100:.0f}% of trades; "
      f"tickers with exactly 1 trade: {(kc==1).sum()} of {len(kc)}")
    sub("Top 25 tickers by trade count")
    for tk, n in kc.head(25).items():
        sd = df[df["ticker"] == tk]["side"].value_counts(normalize=True)
        p(f"  {tk:12} {n:5,}  ({n/len(df)*100:4.1f}%)  long {sd.get('long',0)*100:3.0f}% / short {sd.get('short',0)*100:3.0f}%")

    # ------------------------------------------------------------------
    hdr("3. EXECUTION STYLE & CONVICTION")
    sub("Direction")
    sc = df["side"].value_counts()
    p(f"  long {sc.get('long',0):,} ({sc.get('long',0)/len(df)*100:.1f}%)   "
      f"short {sc.get('short',0):,} ({sc.get('short',0)/len(df)*100:.1f}%)")
    sub("Leverage distribution")
    lev = pd.to_numeric(df["leverage"], errors="coerce").dropna()
    d = lev.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99])
    p(f"  min {d['min']:.0f} | p25 {d['25%']:.0f} | median {d['50%']:.0f} | p75 {d['75%']:.0f} "
      f"| p90 {d['90%']:.0f} | p99 {d['99%']:.0f} | max {d['max']:.0f}")
    sub("Hold time distribution (closed trades)")
    hs = pd.to_numeric(closed["hold_seconds"], errors="coerce").dropna()
    for lbl, lo, hi in [("< 5 min", 0, 300), ("5-15 min", 300, 900), ("15-60 min", 900, 3600),
                        ("1-4 h", 3600, 14400), ("4-24 h", 14400, 86400),
                        ("1-7 d", 86400, 604800), ("> 7 d", 604800, 1e12)]:
        n = ((hs >= lo) & (hs < hi)).sum()
        p(f"  {lbl:10} {n:5,}  ({n/len(hs)*100:4.1f}%)  {'#' * int(40*n/len(hs))}")
    q = hs.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    p(f"  p10 {q.iloc[0]/60:.0f}m | p25 {q.iloc[1]/60:.0f}m | median {q.iloc[2]/3600:.1f}h "
      f"| p75 {q.iloc[3]/3600:.1f}h | p90 {q.iloc[4]/86400:.1f}d")

    # ------------------------------------------------------------------
    hdr("4. RAW PERFORMANCE (Invo self-reported — paper, leveraged, treat with suspicion)")
    ret = pd.to_numeric(closed["return_pct"], errors="coerce").dropna()
    wins, losses = ret[ret > 0], ret[ret <= 0]
    W = len(wins) / len(ret)
    p(f"Win rate:        {W*100:.1f}%")
    p(f"Average win:     +{wins.mean():.1f}%   (median +{wins.median():.1f}%)")
    p(f"Average loss:    {losses.mean():.1f}%   (median {losses.median():.1f}%)")
    p(f"Payoff ratio:    {abs(wins.mean()/losses.mean()):.2f}")
    p(f"Expectancy:      {W*wins.mean() + (1-W)*losses.mean():+.2f}% per trade (on margin)")
    sub("Exit reason breakdown")
    rr = closed.groupby("reason_closed").agg(
        n=("return_pct", "size"), mean_ret=("return_pct", "mean"), median_ret=("return_pct", "median"))
    for r, row in rr.sort_values("n", ascending=False).iterrows():
        p(f"  {r:18} {int(row['n']):6,}  mean {row['mean_ret']:+7.1f}%  median {row['median_ret']:+7.1f}%")
    liq = (closed["is_liquidated"] == True).sum() + (closed["is_liquidated"] == "true").sum()
    p(f"\nLiquidations: {liq:,} ({liq/len(closed)*100:.1f}% of closed trades)")
    sub("Stop-loss / target discipline")
    p(f"  trades with stop_loss set:    {df['stop_loss'].notna().sum():,} ({df['stop_loss'].notna().mean()*100:.0f}%)")
    p(f"  trades with price_target set: {df['price_target'].notna().sum():,} ({df['price_target'].notna().mean()*100:.0f}%)")

    sub("Per-trader breakdown (all traders, sorted by trade count)")
    g = closed.groupby("username").agg(
        n=("return_pct", "size"),
        win=("return_pct", lambda s: (pd.to_numeric(s, errors="coerce") > 0).mean() * 100),
        avg_lev=("leverage", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        med_hold_h=("hold_seconds", lambda s: pd.to_numeric(s, errors="coerce").median() / 3600),
        sum_ret=("return_pct", lambda s: pd.to_numeric(s, errors="coerce").sum()),
        long_pct=("side", lambda s: (s == "long").mean() * 100),
    ).sort_values("n", ascending=False)
    p(f"  {'trader':<16}{'n':>6}{'win%':>7}{'lev':>6}{'hold_h':>8}{'long%':>7}{'sum_ret%':>10}")
    for u, r in g.iterrows():
        p(f"  {u:<16}{int(r['n']):>6}{r['win']:>6.1f}%{r['avg_lev']:>6.1f}{r['med_hold_h']:>8.1f}{r['long_pct']:>6.0f}%{r['sum_ret']:>10.0f}")

    # ------------------------------------------------------------------
    hdr("5. HERDING & SYNCHRONICITY")
    dfs = df.sort_values("t0")
    for w, lbl in [(pd.Timedelta("15min"), "15m"), (pd.Timedelta("1h"), "1h"), (pd.Timedelta("4h"), "4h")]:
        nprev, agree = [], []
        for tk, gg in dfs.groupby("ticker"):
            times, users, sides = gg["t0"].values, gg["username"].values, gg["side"].values
            for i in range(len(gg)):
                m = (times < times[i]) & (times >= times[i] - w)
                others = set(users[m]) - {users[i]}
                nprev.append(len(others))
                if others:
                    agree.append((sides[m] == sides[i]).mean())
        nprev = np.array(nprev)
        p(f"{lbl:>4} window: {(nprev>0).mean()*100:5.1f}% of entries follow >=1 other trader into same coin | "
          f">=2 others: {(nprev>=2).mean()*100:4.1f}% | direction agreement: {np.mean(agree)*100:.0f}%")
    p("\nInterpretation: mostly independent operators; crowding is the exception.")

    # ------------------------------------------------------------------
    if os.path.exists(MATRIX):
        m = pd.read_csv(MATRIX)
        mt = m[m["y_fwd_ret_4h"].notna()].copy()
        hdr(f"6. MARKET STATE AT ENTRY x FORWARD RETURNS  "
            f"({mt['ticker'].nunique()} tickers, {len(mt):,} trades with targets)")
        p("NOTE: forward returns are direction-adjusted, unleveraged, fee-free.")
        p("If built from a partial candle pull this section skews toward top tickers.")
        sub("Forward return summary (their entries) — edge decay curve")
        horder = ["30m", "1h", "2h", "4h", "8h", "12h", "24h", "48h"]
        for hz in horder:
            c = f"y_fwd_ret_{hz}"
            if c not in mt.columns:
                continue
            s = mt[c].dropna() * 100
            if not len(s):
                continue
            p(f"  +{hz:>4}  n={len(s):6,}  mean {s.mean():+.3f}%  median {s.median():+.3f}%  hit {(s>0).mean()*100:.1f}%")
        sub("By side")
        for side, gg in mt.groupby("side"):
            p(f"  {side:5}  1h {gg['y_fwd_ret_1h'].mean()*100:+.3f}%   4h {gg['y_fwd_ret_4h'].mean()*100:+.3f}%   "
              f"24h {gg['y_fwd_ret_24h'].mean()*100:+.3f}%   (n={len(gg):,})")
        sub("MAE / MFE within 24h (stop & target design input)")
        p(f"  MAE (worst adverse): median {mt['y_mae_24h'].median()*100:.2f}%  p25 {mt['y_mae_24h'].quantile(.25)*100:.2f}%  "
          f"p10 {mt['y_mae_24h'].quantile(.10)*100:.2f}%")
        p(f"  MFE (best favorable): median {mt['y_mfe_24h'].median()*100:.2f}%  p75 {mt['y_mfe_24h'].quantile(.75)*100:.2f}%  "
          f"p90 {mt['y_mfe_24h'].quantile(.90)*100:.2f}%")

        def bucket(col, bins, labels, title):
            sub(title)
            gg = mt.groupby(pd.cut(mt[col], bins, labels=labels), observed=True)["y_fwd_ret_4h"]
            for b, s in gg:
                p(f"  {str(b):18} n={len(s):5,}  mean 4h {s.mean()*100:+.3f}%  hit {(s>0).mean()*100:.1f}%")
        bucket("f_vol_z_1h", [-np.inf, 0, 1, 2, np.inf],
               ["quiet (<0)", "normal (0-1)", "elevated (1-2)", "spike (>2)"],
               "Volume z-score at entry -> 4h edge")
        bucket("f_atr_ratio_6_24", [0, 0.7, 1, 1.3, np.inf],
               ["compressed (<0.7)", "normal (0.7-1)", "expanding (1-1.3)", "exploding (>1.3)"],
               "Volatility regime at entry -> 4h edge")
        bucket("f_range_pos_24h", [0, 0.25, 0.5, 0.75, 1],
               ["near 24h low", "low-mid", "high-mid", "near 24h high"],
               "Position in 24h range at entry -> 4h edge")
        bucket("f_park_pctl_30d", [0, 25, 75, 100],
               ["low vol regime", "mid", "high vol regime"],
               "Parkinson vol percentile -> 4h edge")
        bucket("f_cohort_traders_4h", [-1, 0, 1, 3, np.inf],
               ["alone", "1 other", "2-3 others", "4+ others"],
               "Cohort crowding (other traders, prior 4h) -> 4h edge")
        fm = mt[mt["f_fund_pctl_7d"].notna()]
        if len(fm):
            sub("Funding percentile (7d) at entry -> 4h edge  [top tickers only]")
            gg = fm.groupby(pd.cut(fm["f_fund_pctl_7d"], [0, 20, 80, 100],
                                   labels=["low (<20th)", "mid", "high (>80th)"]), observed=True)["y_fwd_ret_4h"]
            for b, s in gg:
                p(f"  {str(b):18} n={len(s):5,}  mean 4h {s.mean()*100:+.3f}%  hit {(s>0).mean()*100:.1f}%")
        sub("Edge by hour of day (UTC) -> 1h fwd")
        gg = mt.groupby("f_hour_utc")["y_fwd_ret_1h"]
        for h, s in gg:
            bar = "#" * max(0, int(s.mean() * 100 / 0.02))
            p(f"  {int(h):02d}:00  n={len(s):4,}  {s.mean()*100:+.3f}%  {bar}")
    else:
        hdr("6. MARKET STATE AT ENTRY — SKIPPED (feature matrix not built yet)")

    # ------------------------------------------------------------------
    hdr("7. DATA INTEGRITY AUDIT")
    p(f"Duplicate trade_ids:        {df['trade_id'].duplicated().sum()}")
    p(f"Trades missing entry_price: {df['entry_price'].isna().sum()}")
    p(f"Trades missing opened_at:   {df['opened_at'].isna().sum()}")
    cl = df[df["closed_at"].notna()].copy()
    cl["tc"] = pd.to_datetime(cl["closed_at"], format="ISO8601")
    p(f"closed_at before opened_at: {(cl['tc'] < cl['t0']).sum()}")
    hs_chk = cl.dropna(subset=["hold_seconds"])
    drift = ((hs_chk["tc"] - hs_chk["t0"]).dt.total_seconds() - pd.to_numeric(hs_chk["hold_seconds"])).abs()
    p(f"hold_seconds disagrees with timestamps by >60s: {(drift > 60).sum()}")
    p(f"entry_price <= 0:           {(pd.to_numeric(df['entry_price'], errors='coerce') <= 0).sum()}")
    p(f"future-dated entries:       {(df['t0'] > pd.Timestamp.now(tz='UTC')).sum()}")
    sub("Null rate of key columns")
    for c in ["leverage", "return_pct", "hold_seconds", "stop_loss", "price_target", "closed_at"]:
        p(f"  {c:14} {df[c].isna().mean()*100:5.1f}% null")
    if os.path.exists(COVERAGE):
        cov = pd.read_csv(COVERAGE)
        done = cov["ticker"].nunique()
        nob = cov[cov["note"].astype(str).str.contains("not on Binance", na=False)]
        p(f"\nBinance pull coverage so far: {done} / {df['ticker'].nunique()} tickers")
        if len(nob):
            nn = df[df["ticker"].isin(nob["ticker"])]
            p(f"Not on Binance futures ({len(nob)} tickers, {len(nn):,} trades): "
              + ", ".join(nob["ticker"].tolist()[:30]))
            p("  -> fall back to Hyperliquid puller (bn/invo_market_data.py) for these.")
    if os.path.exists(MATRIX):
        p(f"Feature matrix rows: {len(m):,} of {len(df):,} trades "
          f"({m['price_mismatch'].sum()} price-mismatch flags)")

    # ------------------------------------------------------------------
    # Sections 8-14 need the feature matrix
    if os.path.exists(MATRIX) and len(mt):
        R = mt["y_fwd_ret_4h"].dropna() * 100  # 4h directional fwd return, %

        hdr("8. RETURN DISTRIBUTION SHAPE & OUTLIER SENSITIVITY")
        p(f"4h fwd return: mean {R.mean():+.3f}%  std {R.std():.2f}%  "
          f"skew {R.skew():+.2f}  kurtosis {R.kurt():.1f} (normal=0)")
        p(f"\nDoes the edge survive removing lucky outliers?")
        p(f"  full mean:            {R.mean():+.3f}%")
        p(f"  drop top 1% trades:   {R[R < R.quantile(0.99)].mean():+.3f}%")
        p(f"  drop top/bot 1%:      {R.clip(R.quantile(0.01), R.quantile(0.99)).mean():+.3f}%  (winsorized)")
        p(f"  drop top/bot 5%:      {R.clip(R.quantile(0.05), R.quantile(0.95)).mean():+.3f}%  (winsorized)")
        p(f"  median:               {R.median():+.3f}%")
        sub("Histogram of 4h fwd returns")
        bins = [-np.inf, -10, -5, -2, -1, -0.5, 0, 0.5, 1, 2, 5, 10, np.inf]
        labels = ["<-10", "-10..-5", "-5..-2", "-2..-1", "-1..-.5", "-.5..0",
                  "0...5", ".5..1", "1..2", "2..5", "5..10", ">10"]
        hcnt = pd.cut(R, bins, labels=labels).value_counts().reindex(labels)
        for b, n in hcnt.items():
            p(f"  {b:>8}%  {n:5,}  {'#' * int(50 * n / hcnt.max())}")
        sub("Class balance (future ML target base rates, 4h horizon)")
        for thr in [0, 0.1, 0.25, 0.5]:
            p(f"  fwd_ret_4h > {thr:+.2f}%:  {(R > thr).mean()*100:.1f}% of trades")

        hdr("9. EDGE STABILITY OVER TIME & BTC REGIME")
        mt["qtr"] = pd.to_datetime(mt["opened_at"], format="ISO8601").dt.to_period("Q").astype(str)
        sub("4h edge by quarter")
        for q, s in mt.groupby("qtr")["y_fwd_ret_4h"]:
            s = s.dropna() * 100
            if len(s) < 20:
                p(f"  {q}  n={len(s):5,}  (too few)")
                continue
            p(f"  {q}  n={len(s):5,}  mean {s.mean():+.3f}%  hit {(s>0).mean()*100:.1f}%")
        btc = load_btc_daily()
        if btc is not None:
            r30 = btc.pct_change(30)
            regime = pd.Series(np.where(r30 > 0.10, "bull", np.where(r30 < -0.10, "bear", "chop")),
                               index=btc.index)
            mt["date"] = pd.to_datetime(mt["opened_at"], format="ISO8601").dt.normalize().dt.tz_localize(None)
            mt["regime"] = mt["date"].map(regime)
            sub("4h edge by BTC regime (30d BTC return: bull >+10%, bear <-10%)")
            for rg, s in mt.groupby("regime")["y_fwd_ret_4h"]:
                s = s.dropna() * 100
                p(f"  {rg:5}  n={len(s):5,}  mean {s.mean():+.3f}%  hit {(s>0).mean()*100:.1f}%")

        hdr("10. PER-TRADER SKILL (our fwd returns, not Invo's numbers)")
        sub("Traders ranked by 4h fwd return after their entries (min 50 matrix rows)")
        g = mt.groupby("username")["y_fwd_ret_4h"].agg(["size", "mean", lambda s: (s > 0).mean()])
        g.columns = ["n", "mean4h", "hit"]
        g = g[g["n"] >= 50].sort_values("mean4h", ascending=False)
        p(f"  {'trader':<16}{'n':>6}{'mean_4h%':>10}{'hit%':>7}")
        for u, r in g.iterrows():
            p(f"  {u:<16}{int(r['n']):>6}{r['mean4h']*100:>+10.3f}{r['hit']*100:>6.1f}%")
        p(f"\n  traders with positive 4h edge: {(g['mean4h'] > 0).sum()} of {len(g)} (with n>=50)")
        sub("Skill persistence: each trader's 1st-half edge vs 2nd-half edge (n>=100)")
        halves = []
        for u, gg in mt.sort_values("t0_ms").groupby("username"):
            s = gg["y_fwd_ret_4h"].dropna()
            if len(s) < 100:
                continue
            h1, h2 = s.iloc[: len(s)//2].mean(), s.iloc[len(s)//2:].mean()
            halves.append((u, h1, h2))
        if len(halves) >= 5:
            hdf = pd.DataFrame(halves, columns=["u", "h1", "h2"])
            rho = hdf[["h1", "h2"]].corr(method="spearman").iloc[0, 1]
            agree = ((hdf["h1"] > 0) == (hdf["h2"] > 0)).mean()
            p(f"  traders tested: {len(hdf)} | rank correlation 1st->2nd half: {rho:+.2f} | "
              f"same-sign edge both halves: {agree*100:.0f}%")
            p("  (positive correlation = skill persists; ~0 = past edge doesn't predict future edge)")

        hdr("11. EXIT QUALITY — money left on the table")
        ex = mt[(mt["status"] == "closed") & mt["y_mfe_24h"].notna()
                & mt["invo_return_pct"].notna() & mt["f_leverage"].notna()].copy()
        ex = ex[ex["f_leverage"] > 0]
        ex["realized_px"] = pd.to_numeric(ex["invo_return_pct"], errors="coerce") / ex["f_leverage"] / 100
        ex = ex[ex["realized_px"].abs() < 1]
        winners = ex[(ex["realized_px"] > 0) & (ex["y_mfe_24h"] > 0)]
        cap = (winners["realized_px"] / winners["y_mfe_24h"]).clip(0, 1.5)
        p(f"Winning trades analyzed: {len(winners):,}")
        p(f"Median capture ratio (realized gain / best available gain in 24h): {cap.median()*100:.0f}%")
        p(f"Winners capturing <25% of the 24h MFE: {(cap < 0.25).mean()*100:.0f}%")
        p(f"Median left on table per winner: {((winners['y_mfe_24h'] - winners['realized_px'])*100).median():.2f}% (unleveraged)")
        p("-> systematic exits have clear room to beat their manual exits.")

        hdr("12. EDGE BY TICKER TIER")
        majors = {"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "LINK", "AVAX", "LTC"}
        mt["tier"] = np.where(mt["ticker"].isin(majors), "major", "altcoin/meme")
        for t, s in mt.groupby("tier")["y_fwd_ret_4h"]:
            s = s.dropna() * 100
            p(f"  {t:12}  n={len(s):5,}  mean 4h {s.mean():+.3f}%  hit {(s>0).mean()*100:.1f}%")
        sub("Top tickers by trade count (4h edge each)")
        for tk, s in mt.groupby("ticker")["y_fwd_ret_4h"]:
            if len(s) < 100:
                continue
            s = s.dropna() * 100
            p(f"  {tk:10}  n={len(s):5,}  mean {s.mean():+.3f}%  hit {(s>0).mean()*100:.1f}%")

        hdr("13. FEATURE INFORMATION COEFFICIENTS & REDUNDANCY")
        p("IC = Spearman rank corr(feature, 4h fwd return). |IC| > 0.03 is meaningful at this n.")
        fcols = [c for c in mt.columns if c.startswith("f_") and mt[c].dtype != object]
        ics = []
        for c in fcols:
            v = mt[[c, "y_fwd_ret_4h"]].dropna()
            if len(v) < 500 or v[c].nunique() < 3:
                continue
            ics.append((c, v[c].corr(v["y_fwd_ret_4h"], method="spearman"), len(v)))
        ics.sort(key=lambda x: -abs(x[1]))
        p(f"  {'feature':<24}{'IC':>8}{'n':>8}")
        for c, ic, n in ics:
            flag = "  <-- " if abs(ic) >= 0.03 else ""
            p(f"  {c:<24}{ic:>+8.3f}{n:>8,}{flag}")
        sub("Highly correlated feature pairs (|spearman| > 0.7) — redundancy for ML")
        cm = mt[fcols].corr(method="spearman")
        seen = set()
        for i, a in enumerate(fcols):
            for b in fcols[i+1:]:
                r = cm.loc[a, b]
                if abs(r) > 0.7 and (a, b) not in seen:
                    seen.add((a, b))
                    p(f"  {a} <-> {b}: {r:+.2f}")
        if not seen:
            p("  none above 0.7")

        hdr("14. NAIVE COHORT EQUITY CURVE & EFFECTIVE SAMPLE SIZE")
        p("Strategy: take every entry, equal weight, hold 4h, unleveraged, fee-free.")
        eq = mt.dropna(subset=["y_fwd_ret_4h"]).sort_values("t0_ms")
        eq["month"] = pd.to_datetime(eq["opened_at"], format="ISO8601").dt.strftime("%Y-%m")
        cum = 0.0
        peak, mdd = 0.0, 0.0
        monthly = eq.groupby("month")["y_fwd_ret_4h"].sum() * 100
        for mo, v in monthly.items():
            cum += v
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
            bar = "#" * int(abs(v) / max(1e-9, monthly.abs().max()) * 30)
            p(f"  {mo}  month {v:+8.1f}%  cum {cum:+9.1f}%  {bar}")
        p(f"\nTotal (sum of per-trade 4h returns): {monthly.sum():+.1f}%  | worst peak-to-trough: {mdd:.1f}%")
        p(f"Months positive: {(monthly > 0).sum()} / {len(monthly)}")
        if btc is not None:
            span = btc[(btc.index >= mt['date'].min()) & (btc.index <= mt['date'].max())]
            if len(span) > 1:
                p(f"BTC buy & hold over same span: {(span.iloc[-1]/span.iloc[0]-1)*100:+.1f}%")
        sub("Effective sample size")
        clusters = eq.assign(blk=eq["t0_ms"] // (4 * 3600 * 1000)).groupby(["ticker", "blk"]).ngroups
        p(f"  {len(eq):,} trades collapse into {clusters:,} independent (ticker x 4h-window) clusters.")
        p("  Significance tests must use the cluster count, not the trade count.")

    # ------------------------------------------------------------------
    if os.path.exists(MATRIX) and len(mt):
        hdr("15. MIXTURE EVIDENCE — this dataset is several behaviors, not one")
        p("Any pooled mean/median above describes a BLEND. The cuts below show the")
        p("distinct ingredients. Proper separation (path clustering) is Phase 3 work.")
        from build_feature_matrix import read_partial_gz_csv
        c15 = read_partial_gz_csv("bn/bn_candles_15m.csv.gz")
        if len(c15):
            by15 = {}
            for tk, g in c15.groupby("ticker"):
                g = g.drop_duplicates("t").sort_values("t")
                by15[tk] = (g["t"].to_numpy("int64"), g["o"].to_numpy(float), g["c"].to_numpy(float))
            M15 = 900_000
            ok = mt[(mt["price_mismatch"] == 0) & mt["y_fwd_ret_30m"].notna()].copy()
            pre, r0 = [], []
            for tr in ok.itertuples():
                d = by15.get(tr.ticker)
                a = b = None
                if d is not None:
                    t, o, c = d
                    i = np.searchsorted(t, tr.t0_ms, side="right") - 1
                    if i >= 0 and tr.t0_ms < t[i] + M15:
                        s = 1 if tr.side == "long" else -1
                        sc = tr.entry_price * (1e6 if str(tr.symbol).startswith("1000000") and not tr.ticker.startswith("1000000")
                                               else 1e3 if str(tr.symbol).startswith("1000") and not tr.ticker.startswith("1000") else 1)
                        a = s * (sc / o[i] - 1)       # candle open -> fill (pre-entry move, trade direction)
                        b = s * (c[i] / sc - 1)       # fill -> first 15m close
                pre.append(a); r0.append(b)
            ok["pre_move"], ok["r_first15"] = pre, r0
            ok = ok[ok["pre_move"].notna()]
            sub("Timing: where the immediate move happens (direction-adjusted means)")
            p(f"  candle open -> fill (before entry):   {ok['pre_move'].mean()*100:+.3f}%  (hit {(ok['pre_move']>0).mean()*100:.0f}%)")
            p(f"  fill -> first 15m close (after):      {ok['r_first15'].mean()*100:+.3f}%  (hit {(ok['r_first15']>0).mean()*100:.0f}%)")
            p(f"  30m -> 24h adds (median path):        {ok['y_fwd_ret_30m'].median()*100:+.2f}% -> {ok['y_fwd_ret_24h'].median()*100:+.2f}%")
            p("  -> typical entry comes AFTER an adverse micro-move; bounce is immediate,")
            p("     then a slow drift continues for hours. Two different clocks.")
            sub("Ingredients by entry type (pre-entry micro-move vs trade direction)")
            ok["entry_type"] = pd.cut(ok["pre_move"], [-np.inf, -0.003, 0.003, np.inf],
                                      labels=["FADE (into adverse move)", "FLAT", "CHASE (with move)"])
            p(f"  {'segment':<28}{'n':>7}{'30m med':>9}{'30m mean':>10}{'24h med':>9}{'24h mean':>10}")
            for seg, g in ok.groupby("entry_type", observed=True):
                p(f"  {str(seg):<28}{len(g):7,}"
                  f"{g['y_fwd_ret_30m'].median()*100:>+9.2f}{g['y_fwd_ret_30m'].mean()*100:>+10.2f}"
                  f"{g['y_fwd_ret_24h'].median()*100:>+9.2f}{g['y_fwd_ret_24h'].mean()*100:>+10.2f}")
            p("  FADE = fast bounce edge (execution-sensitive, fat-tailed).")
            p("  FLAT = slow drift edge (latency-tolerant, most shippable).")
            p("  CHASE = negative-mean failure mode (ban it).")
            p("  Mean/median gaps inside every segment = still mixtures; cluster in Phase 3.")
            sub("Trader style (median hold) x lasting edge")
            stl = ok.groupby("username")["invo_hold_s"].median()
            ok["style"] = ok["username"].map(lambda u: "scalper(<1h)" if stl[u] < 3600
                                             else "intraday(1-8h)" if stl[u] < 28800 else "swing(>8h)")
            for seg, g in ok.groupby("style"):
                p(f"  {seg:<16} n={len(g):6,}  24h median {g['y_fwd_ret_24h'].median()*100:+.2f}%")
            p("  -> cohort scalpers carry no lasting edge; weight them down in training.")

    # ------------------------------------------------------------------
    if os.path.exists(MATRIX) and len(mt):
        hdr("16. CONTROL TEST — their timing vs random timing (the calibration)")
        p("Random same-side entries on the same coins, same period. Controls exclude")
        p("the 24h after any real entry. Full-history tickers only (clean control space).")
        from build_feature_matrix import read_partial_gz_csv as _rpg
        rng = np.random.default_rng(7)
        c1 = _rpg("bn/bn_candles_1h.csv.gz")
        Hms = 3_600_000
        mm = m[m["price_mismatch"] == 0]
        res = []
        for tk, g in c1.groupby("ticker"):
            g = g.drop_duplicates("t").sort_values("t")
            if len(g) < 3000:
                continue
            t = g["t"].to_numpy("int64"); c = g["c"].to_numpy(float)
            trades = mm[mm["ticker"] == tk]
            if len(trades) < 30:
                continue
            valid = np.ones(len(t), bool); valid[-30:] = False
            for ts in trades["t0_ms"].to_numpy("int64"):
                valid[(t >= ts) & (t < ts + 24 * Hms)] = False
            pool = np.where(valid)[0]
            if len(pool) < 500:
                continue
            for _, tr in trades.iterrows():
                s = 1 if tr["side"] == "long" else -1
                res.append({"who": "trader", "1h": tr["y_fwd_ret_1h"],
                            "4h": tr["y_fwd_ret_4h"], "24h": tr["y_fwd_ret_24h"]})
                for j in rng.choice(pool, 5):
                    res.append({"who": "control",
                                **{hz: (s * (c[j + k] / c[j] - 1) if j + k < len(c) else np.nan)
                                   for hz, k in [("1h", 1), ("4h", 4), ("24h", 24)]}})
        r = pd.DataFrame(res)
        if len(r):
            nt, nc = (r["who"] == "trader").sum(), (r["who"] == "control").sum()
            p(f"\ntrader entries: {nt:,} | random controls: {nc:,}")
            p(f"\n  {'horizon':>8} {'traders':>20} {'random control':>20} {'edge vs random':>16}")
            for hz in ["1h", "4h", "24h"]:
                a = r.loc[r["who"] == "trader", hz].dropna() * 100
                b = r.loc[r["who"] == "control", hz].dropna() * 100
                diff = a.mean() - b.mean()
                se = (a.var() / len(a) + b.var() / len(b)) ** 0.5
                p(f"  {hz:>8} {a.mean():+10.3f}% ({(a>0).mean()*100:4.1f}%) "
                  f"{b.mean():+10.3f}% ({(b>0).mean()*100:4.1f}%) {diff:+10.3f}% ({diff/se:+.1f} sd)")
            p("\nCaveats: sd overstated ~2x by trade clustering (see sec 14); trader returns")
            p("use paper fills vs candle closes for controls -> execution realism unresolved.")

    p("")
    p("END OF REPORT")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/eda_report_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
