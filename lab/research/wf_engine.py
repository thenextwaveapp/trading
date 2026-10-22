#!/usr/bin/env python3
"""Walk-forward engine. Run #2 config FROZEN; every order emits a ledger row.

Frozen (from run #2): label = MFE(2h)>=1% & MFE/MAE>=2; wild-negative 5:1 training;
BTC 4h EMA20/50 regime; ADX(14,1h)>30 skip; limit at low+0.25*ATR15 (TTL 2 candles,
strict trade-through); maker 0.015%/leg, taker 0.045%+0.05% slip on stop/time legs;
score threshold = p99 of calibration-window gated scans. Bracket is a parameter
(default run #2: TP 1.5x / SL 1.0x NATR, 8-candle time-out).

Variants: A = bull->longs, bear->shorts (run #2) | B = longs in bull only
          C = longs in bull; shorts in bear only if ticker 1h EMA20<EMA50

Portfolio layer: risk 0.75% of equity per trade (at SL distance), notional cap 20%
of equity, max 6 concurrent, kill-switch: equity -5% vs trailing-7d high -> no new
entries 3 days. Compounded equity, daily Sharpe/Sortino.

Usage:
  python3 wf_engine.py ledger2       # retrofit run #2 window ledger (bt_candles)
  python3 wf_engine.py walkforward   # all windows x variants (wf_candles)
"""
import gzip
import io
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from backtest import hourly_features, MARKET_FEATS, M15, H
from backtest2 import wilder_adx, label_spike, MAKER, TAKER, SLIP

SIGNAL_PCT = 99.0
TTL = 2
NEG_RATIO = 5
DEFAULT_BRACKET = dict(tp=1.5, sl=1.0, hold=8)
PATH_LEN = 24          # candles of post-fill path stored (6h)
RISK = 0.0075
NOTIONAL_CAP = 0.20
MAX_CONC = 6
KILL_DD = -0.05
KILL_LOOKBACK = 7 * 86400_000
KILL_PAUSE = 3 * 86400_000
DAY = 86400_000

WINDOWS = [  # (name, test_start, test_end); cal = 18d pre, warmup = 35d pre
    ("W1-2025Q1", "2025-03-01", "2025-04-15"),
    ("W2-2025Q2", "2025-06-01", "2025-07-15"),
    ("W3-2025Q3", "2025-09-01", "2025-10-15"),
    ("W4-2025Q4", "2025-12-01", "2026-01-15"),
    ("W5-2026Q1", "2026-03-01", "2026-04-15"),
    ("W6-2026Q2", "2026-06-01", "2026-07-15"),
    ("W7-orig", "2026-08-19", "2026-10-03"),
]


def ts(s):
    return int(pd.Timestamp(s, tz="UTC").value // 10**6)


# ---------------------------------------------------------------- data layer
def load_market(c15_path, c1_path):
    c15 = pd.read_csv(c15_path)
    c1 = pd.read_csv(c1_path)

    b = c1[c1["ticker"] == "BTC"].drop_duplicates("t").sort_values("t")
    b4 = b.set_index("t")["c"].groupby(lambda t: t - t % (4 * H)).last()
    e20 = b4.ewm(span=20, adjust=False).mean()
    e50 = b4.ewm(span=50, adjust=False).mean()
    regime_t = b4.index.to_numpy() + 4 * H
    regime_bull = (e20 > e50).to_numpy()

    tickers, grids = {}, {}
    for tk, g15 in c15.groupby("ticker"):
        g15 = g15.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        g1 = c1[c1["ticker"] == tk].drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if len(g1) < 60 or len(g15) < 300:
            continue
        hf = hourly_features(g1).sort_values("close_t")
        adx = wilder_adx(g1).to_numpy()
        tema20 = g1["c"].ewm(span=20, adjust=False).mean().to_numpy()
        tema50 = g1["c"].ewm(span=50, adjust=False).mean().to_numpy()
        t = g15["t"].to_numpy(np.int64)
        o, hh, ll, c, v = (g15[k].to_numpy(float) for k in "ohlcv")
        prev_c = np.concatenate([[c[0]], c[:-1]])
        tr15 = np.maximum(hh, prev_c) - np.minimum(ll, prev_c)
        atr15 = pd.Series(tr15).rolling(14).mean().to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v, atr15=atr15,
                           adx=adx, adx_t=(g1["t"] + H).to_numpy(),
                           tema_bull=(tema20 > tema50), hf=hf)

        # vectorized fast features; contiguity: last 9 candles gapless
        s = g15
        contig = (s["t"].diff() == M15).rolling(9).min() == 1
        grid = pd.DataFrame({
            "ticker": tk, "i": np.arange(len(s)), "t_dec": t + M15, "price": c,
            "raw_pre15": s["c"] / s["c"].shift(1) - 1,
            "raw_pre30": s["c"] / s["c"].shift(2) - 1,
            "raw_pre60": s["c"] / s["c"].shift(4) - 1,
            "raw_prehi": s["c"] / s["h"].shift(1).rolling(4).max() - 1,
            "raw_prelo": s["c"] / s["l"].shift(1).rolling(4).min() - 1,
            "f_vol15_ratio": s["v"] / s["v"].shift(1).rolling(8).mean(),
        })[contig.to_numpy()]
        grid = pd.merge_asof(grid.sort_values("t_dec"), hf, left_on="t_dec",
                             right_on="close_t", direction="backward")
        grids[tk] = grid

    allg = pd.concat(grids.values(), ignore_index=True).dropna(subset=["raw_pre15", "f_ret_24h"])
    dt = pd.to_datetime(allg["t_dec"], unit="ms", utc=True)
    allg["f_hour_utc"] = dt.dt.hour
    allg["f_dow"] = dt.dt.dayofweek

    def regime_at(tsv):
        i = np.searchsorted(regime_t, tsv, "right") - 1
        return None if i < 0 else bool(regime_bull[i])

    return tickers, allg, regime_at


def sided(df, side):
    gs = df.copy()
    gs["f_side_sign"] = side
    for raw, feat in [("raw_pre15", "f_pre15"), ("raw_pre30", "f_pre30"),
                      ("raw_pre60", "f_pre60"), ("raw_prehi", "f_pre_hi1h"),
                      ("raw_prelo", "f_pre_lo1h")]:
        gs[feat] = side * gs[raw]
    return gs


# ------------------------------------------------------------- training layer
_BN15 = None
def bn15_store(need):
    global _BN15
    if _BN15 is None:
        store = {}
        for chunk in pd.read_csv("bn/bn_candles_15m.csv.gz", chunksize=2_000_000):
            for tk, g in chunk[chunk["ticker"].isin(need)].groupby("ticker"):
                store.setdefault(tk, []).append(g[["t", "h", "l"]])
        _BN15 = {tk: (lambda g: (g["t"].to_numpy(np.int64), g["h"].to_numpy(float),
                                 g["l"].to_numpy(float)))(pd.concat(v).drop_duplicates("t").sort_values("t"))
                 for tk, v in store.items()}
    return _BN15


def labeled_trader_entries():
    """Matrix rows with the frozen spike label (computed once, cached to disk)."""
    cache = "master/trader_labels.csv"
    m = pd.read_csv("master/feature_matrix.csv")
    m = m[m["price_mismatch"] == 0].copy()
    if os.path.exists(cache):
        lab = pd.read_csv(cache)
        m = m.merge(lab, on="trade_id", how="inner")
        return m
    from build_feature_matrix import scale_for
    bn = bn15_store(set(m["ticker"]))
    labs = []
    for tr in m.itertuples():
        d = bn.get(tr.ticker)
        lab = np.nan
        if d is not None:
            t_, h_, l_ = d
            a = np.searchsorted(t_, tr.t0_ms, "left")
            b = np.searchsorted(t_, tr.t0_ms + 2 * H, "left")
            if b - a >= 6:
                entry = float(tr.entry_price) * scale_for(tr.ticker, tr.symbol)
                lab, _, _ = label_spike(1 if tr.side == "long" else -1, entry,
                                        pd.Series(h_[a:b]), pd.Series(l_[a:b]))
        labs.append(lab)
    m["lab"] = labs
    m = m.dropna(subset=["lab"])
    m[["trade_id", "lab"]].to_csv(cache, index=False)
    return m


def train_model(mlab, tickers, allg, cut_ms, wild_lo_ms, feats, seed=7):
    tr = mlab[mlab["t0_ms"] < cut_ms]
    pool = allg[(allg["t_dec"] >= wild_lo_ms) & (allg["t_dec"] < cut_ms)].copy()
    ent = {tk: g["t0_ms"].to_numpy(np.int64) for tk, g in tr.groupby("ticker")}
    tdec = pool["t_dec"].to_numpy(np.int64)
    tks = pool["ticker"].to_numpy()
    keep = np.ones(len(pool), bool)
    for j in range(len(pool)):
        e = ent.get(tks[j])
        if e is not None:
            k = np.searchsorted(e, tdec[j])
            if (k < len(e) and e[k] - tdec[j] < 4 * H) or (k > 0 and tdec[j] - e[k - 1] < 4 * H):
                keep[j] = False
    pool = pool[keep]
    rng = np.random.default_rng(seed)
    n = min(len(pool), NEG_RATIO * len(tr))
    wild = pool.iloc[rng.choice(len(pool), n, replace=False)].copy()
    wild["side"] = rng.choice([1, -1], len(wild))
    labs = []
    for r in wild.itertuples():
        d = tickers[r.ticker]
        i = int(r.i)
        b = i + 1 + 8
        if b >= len(d["t"]) or d["t"][i + 1] - d["t"][i] != M15:
            labs.append(np.nan); continue
        lab, _, _ = label_spike(int(r.side), d["c"][i],
                                pd.Series(d["h"][i + 1:b]), pd.Series(d["l"][i + 1:b]))
        labs.append(lab)
    wild["lab"] = labs
    wild = wild.dropna(subset=["lab"])
    wX = sided(wild, 1)
    for raw, feat in [("raw_pre15", "f_pre15"), ("raw_pre30", "f_pre30"),
                      ("raw_pre60", "f_pre60"), ("raw_prehi", "f_pre_hi1h"),
                      ("raw_prelo", "f_pre_lo1h")]:
        wX[feat] = wild["side"].to_numpy() * wild[raw].to_numpy()
    wX["f_side_sign"] = wild["side"].to_numpy()
    X = pd.concat([tr[feats], wX[feats]], ignore_index=True)
    y = np.concatenate([tr["lab"].to_numpy(int), wild["lab"].to_numpy(int)])
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                         validation_fraction=0.15, early_stopping=True,
                                         random_state=7)
    clf.fit(X, y)
    return clf, len(tr), len(wild)


# ------------------------------------------------------------ gating + signals
def allowed(variant, side, bull, tk_bull):
    if bull is None:
        return False
    if variant == "A":
        return (side == 1) == bull
    if variant == "B":
        return side == 1 and bull
    if variant == "C":
        if side == 1:
            return bull
        return (not bull) and (tk_bull is False)
    raise ValueError(variant)


def gated_scores(allg, tickers, regime_at, clf, feats, t0, t1, variant):
    seg = allg[(allg["t_dec"] >= t0) & (allg["t_dec"] < t1)]
    out = []
    for side in (1, -1):
        gs = sided(seg, side)
        bulls = gs["t_dec"].map(regime_at)
        tb = []
        for tk, tv in zip(gs["ticker"], gs["t_dec"]):
            d = tickers[tk]
            i = np.searchsorted(d["adx_t"], tv, "right") - 1
            tb.append(bool(d["tema_bull"][i]) if i >= 0 else None)
        ok = [allowed(variant, side, b, t) for b, t in zip(bulls, tb)]
        gs = gs[pd.Series(ok, index=gs.index)]
        if not len(gs):
            continue
        gs["score"] = clf.predict_proba(gs[feats])[:, 1]
        out.append(gs)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ----------------------------------------------------------------- simulation
def simulate(sig, tickers, bracket, window, variant):
    """Event-driven portfolio sim. Returns (ledger_rows, trade_rows, equity_series)."""
    tp_m, sl_m, hold = bracket["tp"], bracket["sl"], bracket["hold"]
    sig = sig.sort_values("t_dec")
    ledger, trades = [], []
    pending_exits = []           # (exit_t, pnl_abs)
    open_until = {}
    equity, eq_hist = 1.0, []
    kill_until = 0

    for r in sig.itertuples():
        t_now = r.t_dec
        pending_exits.sort()
        while pending_exits and pending_exits[0][0] <= t_now:
            et, pnl = pending_exits.pop(0)
            equity += pnl
            eq_hist.append((et, equity))
        d = tickers[r.ticker]
        i = int(r.i)
        ai = np.searchsorted(d["adx_t"], t_now, "right") - 1
        adx_v = d["adx"][ai] if ai >= 0 else np.nan
        atr = d["atr15"][i]
        row = dict(window=window, variant=variant, ticker=r.ticker, t_signal=t_now,
                   side=int(r.f_side_sign), score=round(r.score, 4),
                   adx=round(float(adx_v), 1) if np.isfinite(adx_v) else np.nan,
                   natr=round(atr / d["c"][i], 5) if np.isfinite(atr) and atr > 0 else np.nan,
                   sig_price=d["c"][i], limit_px=np.nan, filled=0, entry_px=np.nan,
                   t_fill=np.nan, exit_kind="", gross=np.nan, net=np.nan,
                   sig_fwd2h=np.nan, path_h="", path_l="", path_c="", blocked="")
        if i + 8 < len(d["t"]) and d["t"][i + 8] == d["t"][i] + 8 * M15:
            row["sig_fwd2h"] = r.f_side_sign * (d["c"][i + 8] / d["c"][i] - 1)
        if np.isfinite(adx_v) and adx_v > 30:
            row["blocked"] = "adx"; ledger.append(row); continue
        if not np.isfinite(atr) or atr <= 0:
            row["blocked"] = "no_atr"; ledger.append(row); continue
        if open_until.get(r.ticker, 0) > t_now:
            row["blocked"] = "ticker_busy"; ledger.append(row); continue
        if sum(1 for v in open_until.values() if v > t_now) >= MAX_CONC:
            row["blocked"] = "max_conc"; ledger.append(row); continue
        if t_now < kill_until:
            row["blocked"] = "kill_switch"; ledger.append(row); continue
        hist = [e for e in eq_hist if e[0] >= t_now - KILL_LOOKBACK]
        if hist and equity / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_now + KILL_PAUSE
            row["blocked"] = "kill_switch"; ledger.append(row); continue

        side = int(r.f_side_sign)
        natr = atr / d["c"][i]
        lim = d["l"][i] + 0.25 * atr if side == 1 else d["h"][i] - 0.25 * atr
        row["limit_px"] = lim
        fill_j, entry = None, None
        for j in range(i + 1, min(i + 1 + TTL, len(d["t"]))):
            if d["t"][j] - d["t"][j - 1] != M15:
                break
            if side == 1 and d["l"][j] < lim:
                fill_j, entry = j, min(lim, d["o"][j]); break
            if side == -1 and d["h"][j] > lim:
                fill_j, entry = j, max(lim, d["o"][j]); break
        if fill_j is None:
            ledger.append(row); continue

        row["filled"], row["entry_px"], row["t_fill"] = 1, entry, d["t"][fill_j] + M15
        pe = min(fill_j + PATH_LEN, len(d["t"]))
        row["path_h"] = ";".join(f"{x:.5f}" for x in d["h"][fill_j:pe] / entry - 1)
        row["path_l"] = ";".join(f"{x:.5f}" for x in d["l"][fill_j:pe] / entry - 1)
        row["path_c"] = ";".join(f"{x:.5f}" for x in d["c"][fill_j:pe] / entry - 1)

        tp = entry * (1 + side * tp_m * natr)
        sl = entry * (1 - side * sl_m * natr)
        exit_px, exit_kind, j_end = None, None, fill_j
        for j in range(fill_j, min(fill_j + hold, len(d["t"]))):
            j_end = j
            sl_hit = d["l"][j] <= sl if side == 1 else d["h"][j] >= sl
            tp_hit = d["h"][j] >= tp if side == 1 else d["l"][j] <= tp
            if sl_hit:
                exit_px, exit_kind = sl, "sl"; break
            if tp_hit:
                exit_px, exit_kind = tp, "tp"; break
        if exit_px is None:
            exit_px, exit_kind = d["c"][j_end], "time"
        gross = side * (exit_px / entry - 1)
        fees = MAKER + (MAKER if exit_kind == "tp" else TAKER + SLIP)
        net = gross - fees
        notional = min(RISK * equity / max(sl_m * natr, 1e-4), NOTIONAL_CAP * equity)
        pnl = notional * net
        exit_t = d["t"][j_end] + M15
        pending_exits.append((exit_t, pnl))
        open_until[r.ticker] = exit_t
        row["exit_kind"], row["gross"], row["net"] = exit_kind, gross, net
        trades.append(dict(window=window, variant=variant, ticker=r.ticker, t=t_now,
                           side=side, score=r.score, kind=exit_kind, gross=gross,
                           net=net, notional=notional, pnl=pnl))
        ledger.append(row)

    for et, pnl in sorted(pending_exits):
        equity += pnl
        eq_hist.append((et, equity))
    return ledger, trades, eq_hist


def metrics(eq_hist, t0, t1):
    if not eq_hist:
        return dict(ret=0.0, maxdd=0.0, sharpe=np.nan, sortino=np.nan)
    eq = pd.Series({pd.Timestamp(t, unit="ms"): v for t, v in eq_hist}).sort_index()
    daily = eq.resample("1D").last().ffill()
    daily = pd.concat([pd.Series([1.0], index=[daily.index[0] - pd.Timedelta("1D")]), daily])
    r = daily.pct_change().dropna()
    dd = (daily / daily.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    ds = r[r < 0].std()
    sortino = r.mean() / ds * np.sqrt(365) if ds and ds > 0 else np.nan
    return dict(ret=daily.iloc[-1] - 1, maxdd=dd, sharpe=sharpe, sortino=sortino)


# ----------------------------------------------------------------------- main
def run_windows(c15_path, c1_path, windows, variants, bracket, tag):
    feats = MARKET_FEATS
    tickers, allg, regime_at = load_market(c15_path, c1_path)
    mlab = labeled_trader_entries()
    all_ledger, all_trades, win_metrics = [], [], []
    for name, a, b in windows:
        t_test0, t_test1 = ts(a), ts(b)
        t_cal0 = t_test0 - 18 * DAY
        t_wild0 = t_test0 - 35 * DAY
        clf, npos, nneg = train_model(mlab, tickers, allg, t_test0, t_wild0, feats)
        for variant in variants:
            cal = gated_scores(allg, tickers, regime_at, clf, feats, t_cal0, t_test0, variant)
            if len(cal) < 500:
                print(f"{name}/{variant}: insufficient calibration scans ({len(cal)}) — skipped")
                continue
            thr = np.percentile(cal["score"], SIGNAL_PCT)
            test = gated_scores(allg, tickers, regime_at, clf, feats, t_test0, t_test1, variant)
            sig = test[test["score"] >= thr]
            led, trd, eqh = simulate(sig, tickers, bracket, name, variant)
            met = metrics(eqh, t_test0, t_test1)
            n_tr = len(trd)
            net_pt = np.mean([x["net"] for x in trd]) if trd else np.nan
            print(f"{name}/{variant}: train {npos}+{nneg} | thr {thr:.3f} | signals {len(sig)} "
                  f"| trades {n_tr} | net/trade {net_pt*100 if trd else 0:+.3f}% | "
                  f"eq {met['ret']*100:+.2f}% dd {met['maxdd']*100:.2f}%", flush=True)
            all_ledger += led
            all_trades += trd
            win_metrics.append(dict(window=name, variant=variant, trades=n_tr,
                                    net_per_trade=net_pt, **met))
    os.makedirs("backtest", exist_ok=True)
    pd.DataFrame(all_ledger).to_csv(f"backtest/ledger_{tag}.csv.gz", index=False, compression="gzip")
    pd.DataFrame(all_trades).to_csv(f"backtest/trades_{tag}.csv.gz", index=False, compression="gzip")
    pd.DataFrame(win_metrics).to_csv(f"backtest/metrics_{tag}.csv", index=False)
    print(f"artifacts: backtest/ledger_{tag}.csv.gz, trades_{tag}.csv.gz, metrics_{tag}.csv")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ledger2"
    if mode == "ledger2":
        run_windows("backtest/wf_candles_15m.csv.gz", "backtest/wf_candles_1h.csv.gz",
                    [("W7-orig", "2026-08-19", "2026-10-03")], ["A"], DEFAULT_BRACKET, "run2")
    else:
        br = DEFAULT_BRACKET
        if len(sys.argv) > 4:
            br = dict(tp=float(sys.argv[2]), sl=float(sys.argv[3]), hold=int(sys.argv[4]))
        run_windows("backtest/wf_candles_15m.csv.gz", "backtest/wf_candles_1h.csv.gz",
                    WINDOWS, ["A", "B", "C"], br, "wf")
