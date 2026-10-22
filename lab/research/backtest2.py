#!/usr/bin/env python3
"""Run #2: regime-gated, wild-negative-trained, limit-entry, bracket-exit backtest.

Changes vs run #1:
  1. Training = trader entries + 5x wild background points (both correctly labeled)
     Label: MFE_2h >= 1.0% AND MFE_2h/MAE_2h >= 2.0  (asymmetric spike, not drift)
  2. Regime gate: BTC 4h EMA20 vs EMA50 -> bull = longs only, bear = shorts only.
     ADX(14,1h) > 30 on the ticker -> no trade (don't fade strong trends).
  3. Entry: resting limit at signal-candle low + 0.25*ATR15 (mirror for shorts),
     TTL 2 candles, fill only on strict trade-through, maker fee.
  4. Exit: TP +1.5*NATR15 (maker) / SL -1.0*NATR15 (taker+slip) / time out 8
     candles after fill (taker+slip). Same-candle TP&SL conflict -> SL.

Timeline identical to run #1: calibrate Aug 1-18, TEST Aug 19 - Oct 3.
Writes: reports/backtest2_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from backtest import hourly_features, MARKET_FEATS, M15, H, CUT_TEST, CUT_CAL

MAKER = 0.00015
TAKER = 0.00045
SLIP = 0.0005          # extra adverse on stop/market legs
SIGNAL_PCT = 99.0
TTL = 2                # limit order lifetime, candles
MAX_HOLD = 8           # candles after fill
TP_NATR = 1.5
SL_NATR = 1.0
NEG_RATIO = 5
LBL_MFE = 0.01
LBL_RATIO = 2.0

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def wilder_adx(g, n=14):
    h, l, c = g["h"], g["l"], g["c"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=g.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=g.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def label_spike(side, entry, highs, lows):
    """MFE/MAE over the window, direction-adjusted. Returns (label, mfe, mae)."""
    if side == 1:
        mfe = highs.max() / entry - 1
        mae = 1 - lows.min() / entry
    else:
        mfe = 1 - lows.min() / entry
        mae = highs.max() / entry - 1
    mae = max(mae, 1e-6)
    return int(mfe >= LBL_MFE and mfe / mae >= LBL_RATIO), mfe, mae


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    c15 = pd.read_csv("backtest/bt_candles_15m.csv.gz")
    c1 = pd.read_csv("backtest/bt_candles_1h.csv.gz")

    # ---- BTC 4h regime series ----
    b = c1[c1["ticker"] == "BTC"].drop_duplicates("t").sort_values("t")
    b4 = b.set_index("t")["c"].groupby(lambda t: t - t % (4 * H)).last()
    e20 = b4.ewm(span=20, adjust=False).mean()
    e50 = b4.ewm(span=50, adjust=False).mean()
    regime_t = b4.index.to_numpy() + 4 * H  # visible at 4h-bar close
    regime_bull = (e20 > e50).to_numpy()

    def regime_at(ts):
        i = np.searchsorted(regime_t, ts, "right") - 1
        return None if i < 0 else bool(regime_bull[i])

    # ---- per-ticker structures ----
    tickers = {}
    for tk, g15 in c15.groupby("ticker"):
        g15 = g15.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        g1 = c1[c1["ticker"] == tk].drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if len(g1) < 60 or len(g15) < 300:
            continue
        hf = hourly_features(g1).sort_values("close_t")
        adx = wilder_adx(g1)
        adx_t = (g1["t"] + H).to_numpy()
        t = g15["t"].to_numpy(np.int64)
        o = g15["o"].to_numpy(float); hh = g15["h"].to_numpy(float)
        ll = g15["l"].to_numpy(float); c = g15["c"].to_numpy(float)
        v = g15["v"].to_numpy(float)
        prev_c = np.concatenate([[c[0]], c[:-1]])
        tr15 = np.maximum(hh, prev_c) - np.minimum(ll, prev_c)
        atr15 = pd.Series(tr15).rolling(14).mean().to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v, atr15=atr15,
                           hf=hf, adx=adx.to_numpy(), adx_t=adx_t)

    # ---- scan grid with features (same pipeline as run #1) ----
    def build_grid(tk, d):
        t, c, hh, ll, vv = d["t"], d["c"], d["h"], d["l"], d["v"]
        n = len(t)
        cols = {k: np.full(n, np.nan) for k in
                ("pre15", "pre30", "pre60", "prehi", "prelo", "vrat")}
        for i in range(9, n):
            if t[i] - t[i - 1] != M15:
                continue
            cols["pre15"][i] = c[i] / c[i - 1] - 1
            cols["pre30"][i] = c[i] / c[i - 2] - 1
            cols["pre60"][i] = c[i] / c[i - 4] - 1
            cols["prehi"][i] = c[i] / hh[i - 4:i].max() - 1
            cols["prelo"][i] = c[i] / ll[i - 4:i].min() - 1
            mu = vv[i - 8:i].mean()
            cols["vrat"][i] = vv[i] / mu if mu > 0 else np.nan
        grid = pd.DataFrame({"ticker": tk, "i": np.arange(n), "t_dec": t + M15, "price": c,
                             "raw_pre15": cols["pre15"], "raw_pre30": cols["pre30"],
                             "raw_pre60": cols["pre60"], "raw_prehi": cols["prehi"],
                             "raw_prelo": cols["prelo"], "f_vol15_ratio": cols["vrat"]})
        grid = pd.merge_asof(grid.sort_values("t_dec"), d["hf"], left_on="t_dec",
                             right_on="close_t", direction="backward")
        return grid

    grids = {tk: build_grid(tk, d) for tk, d in tickers.items()}
    allg = pd.concat(grids.values(), ignore_index=True).dropna(subset=["raw_pre15", "f_ret_24h"])
    dt = pd.to_datetime(allg["t_dec"], unit="ms", utc=True)
    allg["f_hour_utc"] = dt.dt.hour
    allg["f_dow"] = dt.dt.dayofweek

    def sided(df, side):
        gs = df.copy()
        gs["f_side_sign"] = side
        for raw, feat in [("raw_pre15", "f_pre15"), ("raw_pre30", "f_pre30"),
                          ("raw_pre60", "f_pre60"), ("raw_prehi", "f_pre_hi1h"),
                          ("raw_prelo", "f_pre_lo1h")]:
            gs[feat] = side * gs[raw]
        return gs

    # ---- training set: trader entries + wild background, both labeled by spike rule ----
    m = pd.read_csv("master/feature_matrix.csv")
    m = m[(m["price_mismatch"] == 0) & (m["t0_ms"] < CUT_TEST)].copy()

    # label trader entries from bn 15m candles (chunked read, only needed tickers)
    need = set(m["ticker"])
    store = {}
    for chunk in pd.read_csv("bn/bn_candles_15m.csv.gz", chunksize=2_000_000):
        for tk, g in chunk[chunk["ticker"].isin(need)].groupby("ticker"):
            store.setdefault(tk, []).append(g[["t", "h", "l"]])
    bn15 = {tk: pd.concat(v).drop_duplicates("t").sort_values("t") for tk, v in store.items()}
    bn15 = {tk: (g["t"].to_numpy(np.int64), g["h"].to_numpy(float), g["l"].to_numpy(float))
            for tk, g in bn15.items()}

    ylab = []
    for tr_ in m.itertuples():
        d = bn15.get(tr_.ticker)
        lab = np.nan
        if d is not None:
            t_, h_, l_ = d
            a = np.searchsorted(t_, tr_.t0_ms, "left")
            bnd = np.searchsorted(t_, tr_.t0_ms + 2 * H, "left")
            if bnd - a >= 6:
                side = 1 if tr_.side == "long" else -1
                from build_feature_matrix import scale_for
                entry = float(tr_.entry_price) * scale_for(tr_.ticker, tr_.symbol)
                lab, _, _ = label_spike(side, entry, pd.Series(h_[a:bnd]), pd.Series(l_[a:bnd]))
        ylab.append(lab)
    m["lab"] = ylab
    m = m.dropna(subset=["lab"])
    feats = [f for f in MARKET_FEATS if f in m.columns]

    # wild background: pre-test scan points away from trader entries (+/-4h, same ticker)
    wild_pool = allg[allg["t_dec"] < CUT_TEST].copy()
    ent_by_tk = {tk: g["t0_ms"].to_numpy(np.int64) for tk, g in m.groupby("ticker")}
    keep = np.ones(len(wild_pool), bool)
    tdec = wild_pool["t_dec"].to_numpy(np.int64)
    tks = wild_pool["ticker"].to_numpy()
    for j in range(len(wild_pool)):
        e = ent_by_tk.get(tks[j])
        if e is not None:
            k = np.searchsorted(e, tdec[j])
            if (k < len(e) and e[k] - tdec[j] < 4 * H) or (k > 0 and tdec[j] - e[k - 1] < 4 * H):
                keep[j] = False
    wild_pool = wild_pool[keep]
    rng = np.random.default_rng(7)
    nneg = min(len(wild_pool), NEG_RATIO * len(m))
    wild = wild_pool.iloc[rng.choice(len(wild_pool), nneg, replace=False)].copy()
    wild["side"] = rng.choice([1, -1], len(wild))

    wl = []
    for r in wild.itertuples():
        d = tickers[r.ticker]
        i = r.i
        bnd = i + 1 + 8
        if bnd >= len(d["t"]) or d["t"][i + 1] - d["t"][i] != M15:
            wl.append(np.nan); continue
        lab, _, _ = label_spike(r.side, d["c"][i], pd.Series(d["h"][i + 1:bnd]),
                                pd.Series(d["l"][i + 1:bnd]))
        wl.append(lab)
    wild["lab"] = wl
    wild = wild.dropna(subset=["lab"])
    wild_X = sided(wild, 1)  # placeholder, fix per-row below
    for raw, feat in [("raw_pre15", "f_pre15"), ("raw_pre30", "f_pre30"),
                      ("raw_pre60", "f_pre60"), ("raw_prehi", "f_pre_hi1h"),
                      ("raw_prelo", "f_pre_lo1h")]:
        wild_X[feat] = wild["side"].to_numpy() * wild[raw].to_numpy()
    wild_X["f_side_sign"] = wild["side"].to_numpy()

    Xtr = pd.concat([m[feats], wild_X[feats]], ignore_index=True)
    ytr = np.concatenate([m["lab"].to_numpy(int), wild["lab"].to_numpy(int)])
    p(f"RUN #2 BACKTEST — {stamp}")
    p(f"training: {len(m):,} trader entries (pos rate {m['lab'].mean()*100:.1f}%) "
      f"+ {len(wild):,} wild background (pos rate {wild['lab'].mean()*100:.1f}%)")

    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                         validation_fraction=0.15, early_stopping=True,
                                         random_state=7)
    clf.fit(Xtr, ytr)

    # ---- threshold from calibration window, regime-gated ----
    def gated_scores(df):
        out = []
        for side in (1, -1):
            gs = sided(df, side)
            bull = gs["t_dec"].map(regime_at)
            ok = (bull == True) if side == 1 else (bull == False)  # noqa: E712
            gs = gs[ok.fillna(False)]
            if not len(gs):
                continue
            gs["score"] = clf.predict_proba(gs[feats])[:, 1]
            out.append(gs)
        return pd.concat(out, ignore_index=True) if out else pd.DataFrame()

    cal = gated_scores(allg[(allg["t_dec"] >= CUT_CAL) & (allg["t_dec"] < CUT_TEST)])
    thresh = np.percentile(cal["score"], SIGNAL_PCT)
    p(f"regime gate: BTC 4h EMA20/50 | ADX(14,1h)>30 skip | threshold {thresh:.3f} "
      f"(top {100-SIGNAL_PCT:.0f}% of {len(cal):,} gated calibration scans)")

    # ---- event simulation on test window ----
    test = gated_scores(allg[allg["t_dec"] >= CUT_TEST])
    test = test[test["score"] >= thresh].sort_values("t_dec")
    p(f"test signals after gates+threshold: {len(test):,}")

    trades, busy, placed = [], {}, 0
    for r in test.itertuples():
        d = tickers[r.ticker]
        i = int(r.i)
        if busy.get(r.ticker, 0) > r.t_dec:
            continue
        # ADX gate at signal time
        ai = np.searchsorted(d["adx_t"], r.t_dec, "right") - 1
        if ai >= 0 and d["adx"][ai] > 30:
            continue
        atr = d["atr15"][i]
        if not np.isfinite(atr) or atr <= 0:
            continue
        side = int(r.f_side_sign)
        natr = atr / d["c"][i]
        lim = d["l"][i] + 0.25 * atr if side == 1 else d["h"][i] - 0.25 * atr
        placed += 1
        # fill check: strict trade-through within TTL candles
        fill_j, entry = None, None
        for j in range(i + 1, min(i + 1 + TTL, len(d["t"]))):
            if d["t"][j] - d["t"][j - 1] != M15:
                break
            if side == 1 and d["l"][j] < lim:
                fill_j, entry = j, min(lim, d["o"][j]); break
            if side == -1 and d["h"][j] > lim:
                fill_j, entry = j, max(lim, d["o"][j]); break
        if fill_j is None:
            continue
        tp = entry * (1 + side * TP_NATR * natr)
        sl = entry * (1 - side * SL_NATR * natr)
        exit_px, exit_kind = None, None
        for j in range(fill_j, min(fill_j + MAX_HOLD, len(d["t"]))):
            lo, hi = d["l"][j], d["h"][j]
            sl_hit = lo <= sl if side == 1 else hi >= sl
            tp_hit = hi >= tp if side == 1 else lo <= tp
            if sl_hit:                      # conservative: stop first on conflict
                exit_px, exit_kind = sl, "sl"; break
            if tp_hit:
                exit_px, exit_kind = tp, "tp"; break
        if exit_px is None:
            j = min(fill_j + MAX_HOLD - 1, len(d["t"]) - 1)
            exit_px, exit_kind = d["c"][j], "time"
        gross = side * (exit_px / entry - 1)
        fees = MAKER + (MAKER if exit_kind == "tp" else TAKER + SLIP)
        trades.append({"ticker": r.ticker, "t": r.t_dec, "side": side, "kind": exit_kind,
                       "gross": gross, "net": gross - fees})
        busy[r.ticker] = d["t"][j] + M15

    tdf = pd.DataFrame(trades)
    p("")
    p("=" * 78)
    p(f"RESULTS — TEST 2026-08-19 .. 2026-10-03")
    p(f"orders placed: {placed:,} | filled: {len(tdf):,} "
      f"({len(tdf)/max(placed,1)*100:.0f}% fill rate) | ~{len(tdf)/45:.1f} trades/day")
    if len(tdf):
        p(f"\nnet per trade: mean {tdf['net'].mean()*100:+.3f}%  median {tdf['net'].median()*100:+.3f}%  "
          f"hit {(tdf['net']>0).mean()*100:.1f}%")
        p(f"total net: {tdf['net'].sum()*100:+.1f}%  | gross: {tdf['gross'].sum()*100:+.1f}%")
        eq = tdf["net"].cumsum()
        p(f"max drawdown (equal-weight, additive): {(eq-eq.cummax()).min()*100:.1f}%")
        p("\nby exit kind:")
        for k, g in tdf.groupby("kind"):
            p(f"  {k:5} n={len(g):4,}  net mean {g['net'].mean()*100:+.3f}%")
        p("\nby side: " + " | ".join(
            f"{'long' if s>0 else 'short'}: n={len(g)}, net {g['net'].mean()*100:+.3f}%"
            for s, g in tdf.groupby("side")))
        p("\nby ticker (net total):")
        bt = tdf.groupby("ticker")["net"].agg(["size", "mean", "sum"]).sort_values("sum", ascending=False)
        for tkr, r2 in bt.iterrows():
            p(f"  {tkr:10} n={int(r2['size']):4}  mean {r2['mean']*100:+.3f}%  total {r2['sum']*100:+.2f}%")
        wk = tdf.copy()
        wk["week"] = pd.to_datetime(wk["t"], unit="ms").dt.strftime("%Y-%U")
        p("\nby week (net sum): " + "  ".join(
            f"{w}:{g['net'].sum()*100:+.1f}%" for w, g in wk.groupby("week")))

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/backtest2_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
