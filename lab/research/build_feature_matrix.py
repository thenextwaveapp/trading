#!/usr/bin/env python3
"""Build the point-in-time feature matrix: one row per Invo trade entry.

Left side  (f_*): market state computable strictly from candles CLOSED at/before entry (T0).
Right side (y_*): forward returns and MAE/MFE after T0 — the answer key.

Usage: python3 build_feature_matrix.py [trades_csv] [candles_dir] [out_csv]
Defaults: master/invo_trades_master.csv, bn/, master/feature_matrix.csv

Safe to run while the Binance pull is still writing: partial gzip files are read
up to the last complete block; trades on tickers not yet pulled are skipped and
counted. Re-run after the pull completes to get the full matrix.
"""
import gzip
import io
import math
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

H = 3_600_000
M15 = 900_000

# horizon grid for forward-return targets (hours); 15m candles give the sub-hour resolution
HORIZONS = {"30m": 0.5, "1h": 1, "2h": 2, "4h": 4, "8h": 8, "12h": 12, "24h": 24, "48h": 48}


def read_partial_gz_csv(path):
    """Read a possibly still-being-written gzip CSV up to the last complete block."""
    buf = io.BytesIO()
    try:
        with gzip.open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                buf.write(chunk)
    except (EOFError, OSError):
        pass  # concurrent writer: keep what we got
    buf.seek(0)
    raw = buf.getvalue()
    # drop a possibly truncated final line
    last_nl = raw.rfind(b"\n")
    if last_nl < 0:
        return pd.DataFrame()
    return pd.read_csv(io.BytesIO(raw[: last_nl + 1]))


def ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def scale_for(ticker, symbol):
    """Binance quotes some micro-caps as 1000X/1000000X; rescale entry price to match."""
    if not isinstance(symbol, str):
        return 1.0
    # Invo's k-prefixed tickers (kPEPE, kBONK...) are already in 1000-coin units
    if ticker.startswith("k") and ticker[1:].isupper():
        return 1.0
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    if base.startswith("1000000") and not ticker.startswith("1000000"):
        return 1e6
    if base.startswith("1000") and not ticker.startswith("1000"):
        return 1e3
    return 1.0


def ema(closes, span):
    if len(closes) < span:
        return None
    return pd.Series(closes).ewm(span=span, adjust=False).mean().iloc[-1]


def pct_rank(window_vals, x):
    """Percentile rank of x among window_vals (0-100)."""
    v = window_vals[~np.isnan(window_vals)]
    if len(v) < 8:
        return None
    return float((v <= x).mean() * 100)


def main(trades_csv, candles_dir, out_csv):
    trades = pd.read_csv(trades_csv)
    trades = trades[trades["ticker"].notna() & trades["opened_at"].notna()].copy()
    trades["t0"] = trades["opened_at"].map(ms)

    print("loading candles...")
    c1 = read_partial_gz_csv(f"{candles_dir}/bn_candles_1h.csv.gz")
    c15 = read_partial_gz_csv(f"{candles_dir}/bn_candles_15m.csv.gz")
    fund = read_partial_gz_csv(f"{candles_dir}/bn_funding.csv.gz")
    print(f"  1h rows {len(c1)}, 15m rows {len(c15)}, funding rows {len(fund)}, "
          f"tickers with 1h data: {c1['ticker'].nunique() if len(c1) else 0}")

    by1, by15, byf = {}, {}, {}
    for tk, g in c1.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t")
        by1[tk] = {
            "sym": g["symbol"].iloc[0],
            "t": g["t"].to_numpy(np.int64),
            "o": g["o"].to_numpy(float), "h": g["h"].to_numpy(float),
            "l": g["l"].to_numpy(float), "c": g["c"].to_numpy(float),
            "v": g["v"].to_numpy(float), "tb": g["taker_buy_v"].to_numpy(float),
        }
    for tk, g in c15.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t")
        by15[tk] = {
            "t": g["t"].to_numpy(np.int64),
            "h": g["h"].to_numpy(float), "l": g["l"].to_numpy(float),
            "c": g["c"].to_numpy(float), "v": g["v"].to_numpy(float),
        }
    if len(fund):
        for tk, g in fund.groupby("ticker"):
            g = g.drop_duplicates("time").sort_values("time")
            byf[tk] = (g["time"].to_numpy(np.int64), g["fundingRate"].to_numpy(float))

    # cohort index: per ticker, all entry times/users/sides sorted by time
    coh = {}
    for tk, g in trades.groupby("ticker"):
        g = g.sort_values("t0")
        coh[tk] = (g["t0"].to_numpy(np.int64), g["username"].to_numpy(), g["side"].to_numpy())

    rows, skip_no_candles, skip_short_hist, n_mismatch = [], 0, 0, 0
    for tr in trades.itertuples():
        tk, t0 = tr.ticker, tr.t0
        d1 = by1.get(tk)
        if d1 is None:
            skip_no_candles += 1
            continue
        # candles fully closed at T0: open time + 1h <= t0
        i = np.searchsorted(d1["t"], t0 - H, side="right")  # d1 arrays [0:i] are closed
        if i < 26:
            skip_short_hist += 1
            continue
        t_arr, c_arr, h_arr, l_arr, v_arr, tb_arr = (d1[k][:i] for k in ("t", "c", "h", "l", "v", "tb"))
        # require the trailing window to be contiguous enough (no big gap before entry)
        if t0 - t_arr[-1] > 3 * H:
            skip_short_hist += 1
            continue

        scale = scale_for(tk, d1["sym"])
        entry = float(tr.entry_price) * scale if pd.notna(tr.entry_price) else float(c_arr[-1])
        mismatch = not (0.5 <= entry / c_arr[-1] <= 2.0)
        # dead market: frozen/zero-volume candles around entry (delisted tickers whose
        # Binance feed froze while Invo kept quoting) -> targets are garbage, withhold
        d15chk = by15.get(tk)
        if d15chk is not None:
            a = np.searchsorted(d15chk["t"], t0 - H)
            b = np.searchsorted(d15chk["t"], t0 + 2 * H)
            if b > a:
                vw = d15chk["v"][a:b]
                frozen = d15chk["h"][a:b] == d15chk["l"][a:b]
                if (vw == 0).mean() > 0.3 or frozen.mean() > 0.3:
                    mismatch = True
        if mismatch:
            n_mismatch += 1

        side_sign = 1 if tr.side == "long" else -1
        last = float(c_arr[-1])

        # --- momentum / location ---
        f = {}
        f["ret_1h"] = last / c_arr[-2] - 1
        f["ret_4h"] = last / c_arr[-5] - 1 if i >= 5 else None
        f["ret_24h"] = last / c_arr[-25] - 1
        hi24, lo24 = float(h_arr[-24:].max()), float(l_arr[-24:].min())
        f["dist_high_24h"] = last / hi24 - 1
        f["dist_low_24h"] = last / lo24 - 1
        f["range_pos_24h"] = (last - lo24) / (hi24 - lo24) if hi24 > lo24 else None
        e20, e50 = ema(c_arr[-120:], 20), ema(c_arr[-200:], 50)
        f["ema20_dev"] = last / e20 - 1 if e20 else None
        f["ema50_dev"] = last / e50 - 1 if e50 else None

        # --- volatility ---
        prev_c = np.concatenate(([c_arr[0]], c_arr[:-1]))
        tr_range = np.maximum(h_arr, prev_c) - np.minimum(l_arr, prev_c)
        atr6 = float(tr_range[-6:].mean())
        atr24 = float(tr_range[-24:].mean())
        f["atr_ratio_6_24"] = atr6 / atr24 if atr24 > 0 else None
        f["natr_24h"] = atr24 / last
        w20 = c_arr[-20:]
        sma20, std20 = float(w20.mean()), float(w20.std())
        f["bb_bw_20"] = 4 * std20 / sma20 if sma20 > 0 else None
        with np.errstate(divide="ignore", invalid="ignore"):
            park_sq = np.log(h_arr / l_arr) ** 2 / (4 * math.log(2))
        park_series = pd.Series(park_sq).rolling(24).mean().to_numpy() ** 0.5
        f["park_vol_24h"] = float(park_series[-1]) if not np.isnan(park_series[-1]) else None
        f["park_pctl_30d"] = pct_rank(park_series[-720:], park_series[-1])

        # --- volume ---
        v_hist = v_arr[-25:-1]
        mu, sd = float(v_hist.mean()), float(v_hist.std())
        f["vol_z_1h"] = (float(v_arr[-1]) - mu) / sd if sd > 0 else None
        f["taker_buy_ratio"] = float(tb_arr[-1] / v_arr[-1]) if v_arr[-1] > 0 else None

        # --- funding (top tickers only) ---
        f["fund_rate"] = f["fund_vel"] = f["fund_pctl_7d"] = None
        if tk in byf:
            ft, frates = byf[tk]
            j = np.searchsorted(ft, t0, side="right")
            if j >= 2:
                f["fund_rate"] = float(frates[j - 1])
                f["fund_vel"] = float(frates[j - 1] - frates[j - 2])
                f["fund_pctl_7d"] = pct_rank(frates[max(0, j - 21):j], frates[j - 1])

        # --- fast intra-hour features (15m candles closed before T0 + the live fill price) ---
        # direction-adjusted: negative = price just moved against the trade direction (a fade entry)
        f["pre15"] = f["pre30"] = f["pre60"] = f["pre_hi1h"] = f["pre_lo1h"] = f["vol15_ratio"] = None
        d15f = by15.get(tk)
        if d15f is not None:
            j = np.searchsorted(d15f["t"], t0 - M15, side="right")  # [0:j] fully closed at T0
            if j >= 9 and t0 - d15f["t"][j - 1] <= 3 * M15:         # recent data, no big gap
                c15c, h15, l15, v15 = d15f["c"][:j], d15f["h"][:j], d15f["l"][:j], d15f["v"][:j]
                f["pre15"] = side_sign * (entry / c15c[-1] - 1)
                f["pre30"] = side_sign * (entry / c15c[-2] - 1)
                f["pre60"] = side_sign * (entry / c15c[-4] - 1)
                f["pre_hi1h"] = side_sign * (entry / h15[-4:].max() - 1)
                f["pre_lo1h"] = side_sign * (entry / l15[-4:].min() - 1)
                mu15 = v15[-9:-1].mean()
                f["vol15_ratio"] = float(v15[-1] / mu15) if mu15 > 0 else None

        # --- meta / cohort ---
        f["side_sign"] = side_sign
        f["leverage"] = float(tr.leverage) if pd.notna(tr.leverage) else None
        dt = datetime.fromtimestamp(t0 / 1000, timezone.utc)
        f["hour_utc"] = dt.hour
        f["dow"] = dt.weekday()
        ct, cu, cs = coh[tk]
        for wname, wms in (("1h", H), ("4h", 4 * H), ("24h", 24 * H)):
            a = np.searchsorted(ct, t0 - wms, side="left")
            b = np.searchsorted(ct, t0, side="left")  # strictly before T0
            mask = np.ones(b - a, bool)
            f[f"cohort_n_{wname}"] = int(mask.sum())
            f[f"cohort_traders_{wname}"] = int(len(set(cu[a:b]) - {tr.username}))
        a = np.searchsorted(ct, t0 - 4 * H, side="left")
        b = np.searchsorted(ct, t0, side="left")
        f["cohort_sameside_4h"] = int((cs[a:b] == tr.side).sum())

        # --- targets ---
        y = {f"fwd_ret_{h}": None for h in HORIZONS}
        y.update({"mae_24h": None, "mfe_24h": None, "cov_24h": None})
        if not mismatch:
            d15 = by15.get(tk)

            def price_at(target):
                if d15 is not None:
                    k = np.searchsorted(d15["t"], target, side="right") - 1
                    if k >= 0 and target < d15["t"][k] + M15:
                        return float(d15["c"][k])
                k = np.searchsorted(d1["t"], target, side="right") - 1
                if k >= 0 and target < d1["t"][k] + H:
                    return float(d1["c"][k])
                return None

            for hname, hh in HORIZONS.items():
                p = price_at(t0 + int(hh * H))
                if p is not None:
                    y[f"fwd_ret_{hname}"] = side_sign * (p / entry - 1)
            if d15 is not None:
                a = np.searchsorted(d15["t"], t0, side="left")
                b = np.searchsorted(d15["t"], t0 + 24 * H, side="left")
                if b > a:
                    hi = float(d15["h"][a:b].max()) / entry - 1
                    lo = float(d15["l"][a:b].min()) / entry - 1
                    y["mfe_24h"] = hi if side_sign == 1 else -lo
                    y["mae_24h"] = lo if side_sign == 1 else -hi
                    y["cov_24h"] = round((b - a) / 96, 3)

        rows.append({
            "trade_id": tr.trade_id, "username": tr.username, "ticker": tk,
            "symbol": d1["sym"], "side": tr.side, "opened_at": tr.opened_at, "t0_ms": t0,
            "entry_price": tr.entry_price, "price_mismatch": int(mismatch),
            "invo_return_pct": tr.return_pct, "invo_hold_s": tr.hold_seconds,
            "invo_reason_closed": tr.reason_closed, "status": tr.status,
            **{f"f_{k}": v for k, v in f.items()},
            **{f"y_{k}": v for k, v in y.items()},
        })

    out = pd.DataFrame(rows)
    out.to_csv(out_csv, index=False)
    print(f"\nwrote {out_csv}: {len(out)} rows x {len(out.columns)} cols")
    print(f"skipped: {skip_no_candles} no candle data (ticker not pulled / not on Binance), "
          f"{skip_short_hist} insufficient trailing history")
    print(f"price mismatch flagged (targets withheld): {n_mismatch}")
    if len(out):
        tgt = out["y_fwd_ret_4h"].notna().sum()
        print(f"rows with 4h target: {tgt}")
        print("\nfeature null rates:")
        fc = [c for c in out.columns if c.startswith("f_")]
        nr = out[fc].isna().mean().sort_values(ascending=False)
        print(nr[nr > 0].to_string())


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if len(a) > 0 else "master/invo_trades_master.csv",
         a[1] if len(a) > 1 else "bn",
         a[2] if len(a) > 2 else "master/feature_matrix.csv")
