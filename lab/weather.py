#!/usr/bin/env python3
"""Market weather: instrument FAMILIES swept across their knob ranges.

Measurement only — nothing gates or predicts. Every column is computable
at time t from data available at t. Each family is sampled across a grid
of windows/thresholds instead of one guessed setting; diagnostics (not
taste) decide how many genuinely distinct dials the grid contains.

Usage:
  python3 weather.py            # build backtest/weather.csv.gz + diagnostics
"""
import json
import os
import sys
import time
import urllib.request
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(1, os.path.join(ROOT, "research", "_archive"))

M15 = 900_000
FUND_CACHE = os.path.join(ROOT, "backtest", "btc_funding.csv.gz")
ALMANAC = os.path.join(ROOT, "backtest", "weather.csv.gz")

R_WINDOWS = [1, 2, 4, 8, 16, 24, 48, 72, 120, 168, 336, 720]   # hours
VOL_WINDOWS = [8, 16, 24, 48, 96, 168, 336, 720, 1440]
NATR_WINDOWS = [8, 24, 96, 336]
RSI_1H = [2, 5, 9, 14, 30, 50]
RSI_4H = [2, 5, 9, 14, 30]
BB_WINDOWS = [10, 20, 50, 100]
MACD_PAIRS = [(12, 26), (24, 52), (48, 104)]
EMA_1H = [20, 50, 100, 200, 400, 800]
DD_DAYS = [7, 14, 30, 60, 90, 180]
HIGH_DAYS = [30, 90, 180]
FLUSH_THR = [0.02, 0.03, 0.05, 0.08, 0.10]
UNI_WINDOWS = [1, 4, 24, 72, 168]                               # hours
TAIL_THR = [0.03, 0.05, 0.08, 0.10]
FUND_PRINTS = [1, 3, 9, 21, 90]


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n,
                                                adjust=False).mean()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n,
                                                 adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).to_numpy()


def _days_since(hit):
    out = np.full(len(hit), np.nan)
    last = -1
    for i, x in enumerate(hit):
        if x:
            last = i
        if last >= 0:
            out[i] = (i - last) / 24
    return out


def btc_frame(btc, grid):
    idx = np.searchsorted(btc["t"], grid, side="right") - 1
    ok = idx >= 0
    gv = lambda a: np.where(ok, a[np.clip(idx, 0, None)], np.nan)
    s = pd.DataFrame({"c": gv(btc["c"]), "h": gv(btc["h"]),
                      "l": gv(btc["l"]), "v": gv(btc["v"])})
    out = pd.DataFrame({"t": grid})
    for w in R_WINDOWS:
        out[f"btc_r{w}"] = s["c"] / s["c"].shift(w) - 1
    lr = np.log(s["c"] / s["c"].shift(1))
    for w in VOL_WINDOWS:
        out[f"btc_vol{w}"] = lr.rolling(w).std() * np.sqrt(24)
    pc = s["c"].shift(1)
    tr = np.maximum(s["h"], pc) - np.minimum(s["l"], pc)
    for w in NATR_WINDOWS:
        out[f"btc_natr{w}"] = tr.rolling(w).mean() / s["c"]
    for p in RSI_1H:
        out[f"btc_rsi{p}_1h"] = rsi(s["c"].to_numpy(), p)
    c4 = s["c"].iloc[::4]
    for p in RSI_4H:
        out[f"btc_rsi{p}_4h"] = pd.Series(rsi(c4.to_numpy(), p),
                                          index=c4.index) \
            .reindex(out.index).ffill()
    for n in BB_WINDOWS:
        ma, sd = s["c"].rolling(n).mean(), s["c"].rolling(n).std()
        out[f"btc_bbw{n}"] = 4 * sd / ma
        out[f"btc_bbp{n}"] = (s["c"] - ma) / (2 * sd)
    for a, b in MACD_PAIRS:
        m = s["c"].ewm(span=a).mean() - s["c"].ewm(span=b).mean()
        out[f"btc_macd{a}_{b}"] = (m - m.ewm(span=b // 3).mean()) / s["c"]
    for n in EMA_1H:
        out[f"btc_ema{n}_dist"] = s["c"] / s["c"].ewm(span=n).mean() - 1
    e80, e200 = s["c"].ewm(span=80).mean(), s["c"].ewm(span=200).mean()
    out["btc_ema_bull_4h"] = (e80 > e200).astype(float)   # ~ 4h ema20/50
    for w in DD_DAYS:
        out[f"btc_dd{w}d"] = s["c"] / s["c"].rolling(w * 24).max() - 1
        out[f"btc_ru{w}d"] = s["c"] / s["c"].rolling(w * 24).min() - 1
    for w in HIGH_DAYS:
        out[f"btc_days_hi{w}"] = _days_since(
            (s["c"] >= s["c"].rolling(w * 24).max()).to_numpy())
    r24 = out["btc_r24"]
    for thr in FLUSH_THR:
        out[f"btc_days_flush{int(thr*100)}"] = _days_since(
            (r24 <= -thr).to_numpy())
    for w in (168, 720):
        out[f"btc_volu24_{w}"] = s["v"].rolling(24).sum() / \
            s["v"].rolling(w).sum() * (w / 24)
    return out


def universe_frame(tickers, panel, tks, grid):
    """Cross-sectional families at several horizons, from per-ticker data."""
    alive = panel["alive"]
    idx = panel["idx"]
    n_rows = len(grid)
    out = pd.DataFrame({"t": grid})
    out["uni_n"] = alive.sum(axis=1).astype(float)
    # per-horizon return matrix built from each ticker's own series
    for w in UNI_WINDOWS:
        bars = 4 * w
        R = np.full((n_rows, len(tks)), np.nan)
        for j, tk in enumerate(tks):
            c, t = tickers[tk]["c"], tickers[tk]["t"]
            ij = idx[:, j]
            v = alive[:, j] & (ij >= bars)
            ij0 = np.clip(ij - bars, 0, None)
            gap = t[ij] - t[ij0] != bars * M15
            v &= ~gap
            with np.errstate(invalid="ignore", divide="ignore"):
                r = c[ij] / c[ij0] - 1
            R[v, j] = r[v]
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[f"uni_breadth{w}"] = np.nanmean(R < 0, axis=1)
            out[f"uni_med{w}"] = np.nanmedian(R, axis=1)
            out[f"uni_disp{w}"] = np.nanstd(R, axis=1)
            q75 = np.nanpercentile(R, 75, axis=1)
            q25 = np.nanpercentile(R, 25, axis=1)
            out[f"uni_iqr{w}"] = q75 - q25
            if w == 24:
                for thr in TAIL_THR:
                    out[f"uni_tail_dn{int(thr*100)}"] = \
                        np.nanmean(R <= -thr, axis=1)
                    out[f"uni_tail_up{int(thr*100)}"] = \
                        np.nanmean(R >= thr, axis=1)
    rpos = np.where(alive, panel["rpos"], np.nan)
    natr = np.where(alive, panel["natr"], np.nan)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out["uni_med_rpos"] = np.nanmedian(rpos, axis=1)
        out["uni_med_natr"] = np.nanmedian(natr, axis=1)
    return out


def fetch_funding(symbol="BTCUSDT"):
    if os.path.exists(FUND_CACHE):
        return pd.read_csv(FUND_CACHE)
    rows, t0 = [], 1672531200000
    while True:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
               f"&startTime={t0}&limit=1000")
        chunk = json.loads(urllib.request.urlopen(url, timeout=30).read())
        if not chunk:
            break
        rows += [(int(r["fundingTime"]), float(r["fundingRate"]))
                 for r in chunk]
        t0 = rows[-1][0] + 1
        if len(chunk) < 1000:
            break
        time.sleep(0.3)
    df = pd.DataFrame(rows, columns=["t", "rate"])
    df.to_csv(FUND_CACHE, index=False)
    return df


def funding_cols(grid):
    try:
        f = fetch_funding()
    except Exception as e:
        print(f"WARN funding fetch failed: {e!r} — columns NaN")
        return pd.DataFrame({"t": grid} | {
            f"btc_fund{n}": np.nan for n in FUND_PRINTS})
    idx = np.searchsorted(f["t"].to_numpy(), grid, side="right") - 1
    rate = pd.Series(np.where(idx >= 0,
                              f["rate"].to_numpy()[np.clip(idx, 0, None)],
                              np.nan))
    out = pd.DataFrame({"t": grid})
    for n in FUND_PRINTS:
        out[f"btc_fund{n}"] = rate if n == 1 else \
            rate.rolling(n).mean().to_numpy()
    return out


def build():
    from regime_switch_backtest import load_full
    from hourly_explore import precompute, build_panel
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    grid = np.asarray(grid, dtype=np.int64)
    w = btc_frame(tickers["BTC"], grid) \
        .merge(universe_frame(tickers, panel, tks, grid), on="t") \
        .merge(funding_cols(grid), on="t")
    for uw in UNI_WINDOWS:
        if f"btc_r{uw}" in w and f"uni_med{uw}" in w:
            w[f"alt_spread{uw}"] = w[f"uni_med{uw}"] - w[f"btc_r{uw}"]
    w.to_csv(ALMANAC, index=False)
    print(f"almanac: {len(w):,} rows x {len(w.columns)-1} instruments "
          f"-> {ALMANAC}")
    return w


def diagnose(w):
    lines = []
    p = lambda s="": (lines.append(s), print(s))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cols = [c for c in w.columns if c != "t"]
    X = w[cols]
    p(f"WEATHER GRID DIAGNOSTICS — {stamp}")
    p(f"{len(w):,} hourly rows, {len(cols)} instruments\n")

    corr = X.rank().corr()           # spearman via ranks (one pass)
    p("A. EFFECTIVE DIALS — connected components of |rho|>=thr graph")
    import collections
    for thr in (0.95, 0.9, 0.8, 0.7):
        parent = {c: c for c in cols}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                r = corr.loc[a, b]
                if np.isfinite(r) and abs(r) >= thr:
                    parent[find(a)] = find(b)
        comp = collections.defaultdict(list)
        for c in cols:
            comp[find(c)].append(c)
        p(f"  thr {thr}: {len(comp)} components")
        if thr == 0.8:
            p("\n  components at 0.8 (the dial map):")
            for k, mem in sorted(comp.items(), key=lambda x: -len(x[1])):
                p(f"    [{len(mem):2d}] {', '.join(sorted(mem))}")

    p("\nB. PCA — components to explain variance (rank-standardized,"
      " complete rows)")
    Z = X.rank()
    Z = (Z - Z.mean()) / Z.std()
    Zc = Z.dropna()
    ev = np.linalg.eigvalsh(np.cov(Zc.to_numpy().T))[::-1]
    cum = np.cumsum(ev) / ev.sum()
    for v in (0.8, 0.9, 0.95, 0.99):
        p(f"  {int(v*100)}% variance: {int(np.searchsorted(cum, v)) + 1} components")

    p("\nC. HALF-LIFE LADDER (hours to autocorr<0.5), per family")
    fams = {}
    for c in cols:
        fam = c.rstrip("0123456789_hd")
        fams.setdefault(fam, []).append(c)
    for fam in sorted(fams):
        hls = []
        for c in fams[fam]:
            s = w[c].dropna()
            if len(s) < 1000:
                continue
            hl = ">1k"
            for lag in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024):
                if s.autocorr(lag) < 0.5:
                    hl = lag
                    break
            hls.append(f"{c.split('_',1)[1]}:{hl}")
        p(f"  {fam:14s} {' '.join(hls)}")

    out = os.path.join(ROOT, "reports",
                       f"weather_grid_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    diagnose(build())
