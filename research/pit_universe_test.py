#!/usr/bin/env python3
"""POINT-IN-TIME UNIVERSE TEST — Super Larry with zero universe lookahead.

The static universe60 was built from the Invo traders' FULL trade history
(Feb 2024 -> Oct 2026), so backtests before ~2025 lean on future attention.
This rerun makes the universe causal: at each month start, universe =
top-65 tickers by Invo trade count over the TRAILING 180 days (>= 3
trades), mapped to Binance perps (candles from r60 + wide caches, delisted
included). Signals AND dial events only count while their ticker is in the
point-in-time universe. Trading window 2024-06-01 .. today (the trade log
is too thin before mid-2024 to define a universe honestly).

Control arm: the static 60 over the identical window — the gap between the
two is the size of the universe-lookahead inflation.

Usage: python3 research/pit_universe_test.py
Writes: reports/pit_universe_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import H, M15
from degen_derby import precompute, sig_pump, sig_capit, resolve, START
from regime_switch_backtest import make_dial
from core import regime

WDAYS, THR = 30, 0.0
TRAIL = pd.Timedelta(days=180)
TOP_N, MIN_TRADES = 65, 3
T_DATA = int(pd.Timestamp("2024-01-01", tz="UTC").value // 10**6)
T_TRADE = int(pd.Timestamp("2024-06-01", tz="UTC").value // 10**6)
USECOLS = ["ticker", "t", "o", "h", "l", "c", "v"]
CACHES_15 = ["backtest/r60_oos_15m.csv.gz", "backtest/r60_candles_15m.csv.gz",
             "backtest/wide_15m.csv.gz"]
CACHES_1H = ["backtest/r60_oos_1h.csv.gz", "backtest/r60_candles_1h.csv.gz",
             "backtest/wide_1h.csv.gz"]

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def variants(tk):
    return [tk, f"k{tk}", f"1000{tk}", f"1000000{tk}"]


def monthly_universes():
    """-> (month_starts_ms, [set(trade_tickers)]) — causal snapshots."""
    tr = pd.read_csv("master/invo_trades_master.csv",
                     usecols=["ticker", "opened_at"])
    tr["ts"] = pd.to_datetime(tr["opened_at"], utc=True, format="mixed")
    months = pd.date_range("2024-04-01", "2026-10-01", freq="MS", tz="UTC")
    starts, sets = [], []
    for m in months:
        w = tr[(tr["ts"] >= m - TRAIL) & (tr["ts"] < m)]
        cnt = w["ticker"].value_counts()
        cnt = cnt[cnt >= MIN_TRADES]
        sets.append(set(cnt.index[:TOP_N]))
        starts.append(int(m.value // 10**6))
    return np.array(starts, np.int64), sets


def load_candles(cand_names):
    """Merged per-ticker arrays (t >= T_DATA) for any ticker in cand_names,
    across r60 + wide caches; shaped like rules_backtest.load. Also returns
    regime_at (BTC 4h EMA20/50) built from the merged BTC 1h series."""
    frames15, frames1h = {}, {}
    for paths, acc in [(CACHES_15, frames15), (CACHES_1H, frames1h)]:
        for path in paths:
            for ch in pd.read_csv(path, usecols=USECOLS, chunksize=4_000_000):
                ch = ch[(ch["t"] >= T_DATA) & ch["ticker"].isin(cand_names)]
                for tk, g in ch.groupby("ticker"):
                    acc.setdefault(tk, []).append(g)
    tickers = {}
    btc_1h = None
    for tk, parts in frames15.items():
        if tk not in frames1h:
            continue
        g = pd.concat(parts).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        g1 = pd.concat(frames1h[tk]).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        if tk == "BTC":
            btc_1h = g1
        if len(g) < 500 or len(g1) < 100:
            continue
        t = g["t"].to_numpy(np.int64)
        o, hh, ll, c, v = (g[k].to_numpy(float) for k in "ohlcv")
        prev = np.concatenate([[g1["c"].iloc[0]], g1["c"].to_numpy()[:-1]])
        tr = np.maximum(g1["h"].to_numpy(), prev) - \
            np.minimum(g1["l"].to_numpy(), prev)
        natr24 = pd.Series(tr).rolling(24).mean().to_numpy() / g1["c"].to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v,
                           natr_t=(g1["t"] + H).to_numpy(), natr=natr24)
    s = btc_1h.set_index("t")["c"].groupby(lambda x: x - x % (4 * H)).last()
    e20 = s.ewm(span=20, adjust=False).mean()
    e50 = s.ewm(span=50, adjust=False).mean()
    rt = s.index.to_numpy() + 4 * H
    rb = (e20 > e50).to_numpy()

    def regime_at(tsv):
        i = np.searchsorted(rt, tsv, "right") - 1
        return None if i < 0 else bool(rb[i])
    return tickers, regime_at


def run_book_pit(tickers, dial, regime_at, cfg, member, legs=("S", "C")):
    """SL.run_book with a point-in-time membership check on every signal."""
    rows = []
    for tk, d in tickers.items():
        if "S" in legs:
            ii, _ = sig_pump(d)
            rows += [(d["t"][i] + M15, tk, i, "S") for i in ii
                     if d["t"][i] + M15 >= T_TRADE and member(tk, d["t"][i])]
        if "C" in legs:
            ii, _ = sig_capit(d, drop=0.20)
            rows += [(d["t"][i] + M15, tk, i, "C") for i in ii
                     if d["t"][i] + M15 >= T_TRADE and member(tk, d["t"][i])]
    rows.sort()

    eq, peak, maxdd = START, START, 0.0
    pending, open_until, open_leg = [], {}, {}
    n_s = n_c = skipped = liqs = 0
    for t_sig, tk, i, leg in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl, lq = pending.pop(0)
            eq += pnl
            liqs += lq
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq < START * 0.001:
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        conc = sum(1 for k, x in open_until.items()
                   if x > t_sig and open_leg.get(k) == leg)
        if leg == "S":
            if conc >= 4:
                continue
            if dial(t_sig)[0] != -1:
                skipped += 1
                continue
        else:
            if conc >= 3:
                continue
            if regime_at(t_sig) is not False:
                skipped += 1
                continue
        d = tickers[tk]
        frac0, lev, pw, cap = cfg[leg]
        if leg == "S":
            net, exit_t, kind = resolve(d, i, "short", 96, "4hhigh", lev)
            scale = d["runup_v"][i] / 0.12
        else:
            net, exit_t, kind = resolve(d, i, "long", 192, "none", lev)
            scale = -d["drop96_v"][i] / 0.20
        frac = min(frac0 * scale ** pw, cap)
        margin = min(frac * eq, eq)
        pnl = max(margin * lev * net, -margin)
        pending.append((exit_t, pnl, kind == "LIQUIDATED"))
        open_until[tk] = exit_t
        open_leg[tk] = leg
        if leg == "S":
            n_s += 1
        else:
            n_c += 1
    for et, pnl, lq in sorted(pending):
        eq += pnl
        liqs += lq
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    return max(eq, 0.0), maxdd, n_s, n_c, skipped, liqs


def pit_dial(tickers, member):
    """gate30 dial fed only by events whose ticker was in the PIT universe
    at event time."""
    et, er, ed = [], [], []
    for tk, d in tickers.items():
        a, b, c = regime.pump_events_15m({tk: d})
        keep = [j for j in range(len(a)) if member(tk, int(a[j]))]
        et += [a[j] for j in keep]
        er += [b[j] for j in keep]
        ed += [c[j] for j in keep]
    order = np.argsort(et)
    et = np.array(et)[order]
    er = np.array(er)[order]
    ed = np.array(ed)[order]
    return make_dial(et, er, ed, WDAYS, THR), len(et)


LADDER = [
    ("Super Monk  (4%/1x both, flat)",
     dict(S=(0.04, 1, 0.0, 0.08), C=(0.04, 1, 0.0, 0.08))),
    ("Super Eddie (20%/1x both, flat)",
     dict(S=(0.20, 1, 0.0, 0.20), C=(0.20, 1, 0.0, 0.20))),
    ("Super Harry (S 25%/2x quad c50, C 25%/1x)",
     dict(S=(0.25, 2, 2.0, 0.50), C=(0.25, 1, 1.0, 0.50))),
    ("SUPER LARRY — FINAL SPEC (S 25%/3x quad c50, C 25%/2x lin c30)",
     dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30))),
    ("Super Larry MAX (S 35%/3x quad c75, C 35%/2x lin c75)",
     dict(S=(0.35, 3, 2.0, 0.75), C=(0.35, 2, 1.0, 0.75))),
]


def run_arm(tag, tickers, dial, regime_at, member):
    p(f"  [{tag}]")
    p(f"  {'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>5s} {'C':>5s} "
      f"{'skip':>6s} {'liq':>4s}")
    for name, cfg in LADDER:
        eq, maxdd, n_s, n_c, sk, lq = run_book_pit(
            tickers, dial, regime_at, cfg, member)
        p(f"  {name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")
    cfg = LADDER[3][1]
    for legs, nm in [(("S",), "  -> leg S alone (Larry sizing)"),
                     (("C",), "  -> leg C alone (Larry sizing)")]:
        eq, maxdd, n_s, n_c, sk, lq = run_book_pit(
            tickers, dial, regime_at, cfg, member, legs=legs)
        p(f"  {nm:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")


def main():
    import json
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"POINT-IN-TIME UNIVERSE TEST — {stamp}")
    p(f"universe at month M = top-{TOP_N} Invo tickers by trade count in "
      f"[M-180d, M), >= {MIN_TRADES} trades; window 2024-06 .. today")
    p("")

    starts, usets = monthly_universes()
    p("universe size by month:")
    for s, u in zip(starts, usets):
        d = pd.to_datetime(s, unit="ms")
        p(f"  {d.strftime('%Y-%m')}: {len(u):3d}")
    p("")

    # candle-name candidates for every ticker that ever makes a universe
    all_trade_tks = set().union(*usets)
    cand = set()
    for tk in all_trade_tks:
        cand.update(variants(tk))
    p(f"{len(all_trade_tks)} distinct trade tickers ever in a PIT universe")
    print("loading candles (r60 + wide, 2024-01 ..) ...", flush=True)
    tickers, regime_at = load_candles(cand)
    for d in tickers.values():
        precompute(d)
    # candle ticker -> trade ticker (prefer exact name)
    t2c = {}
    for tk in all_trade_tks:
        for vname in variants(tk):
            if vname in tickers:
                t2c.setdefault(tk, vname)
                break
    c2t = {v: k for k, v in t2c.items()}
    p(f"{len(tickers)} candle tickers loaded, {len(c2t)} matched to trades")

    def member_pit(candle_tk, t):
        tk = c2t.get(candle_tk)
        if tk is None:
            return False
        i = int(np.searchsorted(starts, t, "right") - 1)
        return i >= 0 and tk in usets[i]

    u60 = set(json.load(open("paper/universe60.json")))

    def member_60(candle_tk, t):
        return candle_tk in u60

    dial_p, nev = pit_dial(tickers, member_pit)
    p(f"PIT dial events: {nev:,}")
    run_arm("POINT-IN-TIME universe (no lookahead)", tickers, dial_p,
            regime_at, member_pit)
    p("")
    dial_s, nev = pit_dial(tickers, member_60)
    p(f"static-60 dial events: {nev:,}")
    run_arm("STATIC 60 (the lookahead universe), same window", tickers,
            dial_s, regime_at, member_60)

    fname = ("reports/pit_universe_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
