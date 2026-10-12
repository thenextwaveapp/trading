#!/usr/bin/env python3
"""THE DEGEN DERBY — whimsical backtest race.

Every racer starts with $10,000 on the same track (the r60 cache,
Mar 2025 -> Oct 2026, 60 tickers, 15m candles). Params, sizing, leverage,
stops: all fudged per racer. Compounding on. Liquidations on. Kill-switches
mostly thrown in the bin. Most money at the finish line wins.

This is EXPLORATION, not validation. The winner is probably overfit and
we love them anyway.

Usage: python3 degen_derby.py
Writes: reports/degen_derby_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load, TAKER, SLIP
from backtest import M15

START = 10_000.0
COST = 2 * TAKER + SLIP          # round-trip taker + slip, per unit notional

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


# ----------------------------------------------------------- precompute
def precompute(d):
    t, c, v, h, l = d["t"], d["c"], d["v"], d["h"], d["l"]
    n = len(t)
    gap_ok = np.zeros(n, bool)
    gap_ok[16:] = (t[16:] - t[:-16]) == 16 * M15
    vall = pd.Series(v > 0).rolling(9).min().to_numpy() == 1
    d["alive_v"] = gap_ok & vall & (h != l) & (np.arange(n) >= 100)
    ru = np.full(n, np.nan)
    ru[16:] = c[16:] / c[:-16] - 1
    d["runup_v"] = ru
    dr = np.full(n, np.nan)
    dr[96:] = c[96:] / c[:-96] - 1
    d["drop96_v"] = dr
    wk = np.zeros(n, bool)
    wk[1:] = c[1:] < c[:-1]
    d["weak_v"] = wk
    mu = pd.Series(v).rolling(8).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["volr_v"] = np.where(mu > 0, v / mu, np.nan)


# ----------------------------------------------------------- signal gens
def sig_pump(d, runup=0.12, volx=2.0, weak=True):
    cond = d["alive_v"] & (d["runup_v"] >= runup) & (d["volr_v"] >= volx)
    if weak:
        cond = cond & d["weak_v"]
    return np.nonzero(cond)[0], "short"


def sig_capit(d, drop=0.20):
    cond = d["alive_v"] & (d["drop96_v"] <= -drop)
    # debounce: only first bar of a qualifying streak
    first = np.concatenate([[True], ~cond[:-1]])
    return np.nonzero(cond & first)[0], "long"


def sig_chase(d, runup=0.12, volx=2.0):
    """Buy the pump, green candle. We PROVED this loses post-2025. He raced anyway."""
    strong = ~d["weak_v"]
    cond = d["alive_v"] & (d["runup_v"] >= runup) & (d["volr_v"] >= volx) & strong
    return np.nonzero(cond)[0], "long"


# ----------------------------------------------------------- trade resolver
def resolve(d, i, side, hold, stop_mode, lev):
    """Walk the path. Returns (net_on_notional, exit_t, kind).
    net is gross move in our favor minus costs; liquidation caps at -1/lev."""
    t, h, l, c = d["t"], d["h"], d["l"], d["c"]
    entry = c[i]
    n = len(t)
    end = min(i + hold, n - 1)
    liq = 1.0 / lev - 0.005 if lev > 1 else np.inf  # adverse move that wipes margin

    if side == "short":
        base_sl = h[max(i - 16, 0):i + 1].max()
        sl_level = {"4hhigh": base_sl, "buf2": base_sl * 1.02,
                    "tight": entry * 1.02, "none": np.inf}[stop_mode]
        liq_price = entry * (1 + liq)
        for j in range(i + 1, end + 1):
            if h[j] >= liq_price:
                return -liq - COST, t[j] + M15, "LIQUIDATED"
            if h[j] > sl_level:
                return -(sl_level / entry - 1) - COST, t[j] + M15, "sl"
        return -(c[end] / entry - 1) - COST, t[end] + M15, "time"
    else:
        sl_level = {"4hhigh": -np.inf, "buf2": -np.inf,
                    "tight": entry * 0.98, "none": -np.inf,
                    "ds15": entry * 0.85}[stop_mode]
        liq_price = entry * (1 - liq)
        for j in range(i + 1, end + 1):
            if l[j] <= liq_price:
                return -liq - COST, t[j] + M15, "LIQUIDATED"
            if l[j] <= sl_level:
                return (sl_level / entry - 1) - COST, t[j] + M15, "sl"
        return (c[end] / entry - 1) - COST, t[end] + M15, "time"


# ----------------------------------------------------------- the race engine
def race(name, tickers, siggen, sigkw, hold, stop_mode, frac, lev,
         max_conc, martingale=False):
    rows = []
    for tk, d in tickers.items():
        ii, side = siggen(d, **sigkw)
        rows += [(d["t"][i] + M15, tk, i, side) for i in ii]
    rows.sort()

    equity, peak, maxdd = START, START, 0.0
    eq_curve = [(rows[0][0] if rows else 0, START)]
    pending, open_until = [], {}
    trades = wins = liqs = 0
    mart_mult = 1.0
    busted_at = None

    for t_sig, tk, i, side in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl, won, liq = pending.pop(0)
            equity += pnl
            wins += won
            liqs += liq
            peak = max(peak, equity)
            maxdd = min(maxdd, equity / peak - 1)
            eq_curve.append((et, equity))
            if martingale:
                mart_mult = 1.0 if won else min(mart_mult * 2, 8)
        if equity < START * 0.01:
            busted_at = t_sig
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= max_conc:
            continue
        d = tickers[tk]
        net, exit_t, kind = resolve(d, i, side, hold, stop_mode, lev)
        margin = frac * equity * (mart_mult if martingale else 1.0)
        margin = min(margin, equity)  # can't post more than you have
        notional = margin * lev
        pnl = max(notional * net, -margin)
        pending.append((exit_t, pnl, net > 0, kind == "LIQUIDATED"))
        open_until[tk] = exit_t
        trades += 1

    for et, pnl, won, liq in sorted(pending):
        equity += pnl
        wins += won
        liqs += liq
        peak = max(peak, equity)
        maxdd = min(maxdd, equity / peak - 1)
        eq_curve.append((et, equity))

    equity = max(equity, 0.0)
    return dict(name=name, final=equity, ret=equity / START - 1, trades=trades,
                win=wins / trades if trades else 0.0, maxdd=maxdd, liqs=liqs,
                busted=busted_at is not None, curve=eq_curve)


# ----------------------------------------------------------- the field
def build_field():
    PS = sig_pump
    return [
        # name, siggen, sigkw, hold, stop, frac, lev, conc, martingale
        ("The Monk (frozen rule, by the book)", PS, dict(), 16, "4hhigh", 0.04, 1, 6, False),
        ("Steady Eddie (20% flat)",            PS, dict(), 16, "4hhigh", 0.20, 1, 6, False),
        ("Half-Port Harry",                    PS, dict(), 16, "4hhigh", 0.50, 1, 4, False),
        ("Full Port Frank (100%, no lev)",     PS, dict(), 16, "4hhigh", 1.00, 1, 1, False),
        ("Leverage Larry (25% at 4x)",         PS, dict(), 16, "4hhigh", 0.25, 4, 4, False),
        ("Degen Dave (full port 5x)",          PS, dict(), 16, "4hhigh", 1.00, 5, 1, False),
        ("Absolute Unit (full port 10x, no stop)", PS, dict(), 16, "none", 1.00, 10, 1, False),
        ("Sniper Sue (20%+4x vol, 50% at 3x)", PS, dict(runup=0.20, volx=4.0), 16, "4hhigh", 0.50, 3, 2, False),
        ("Scattergun Sam (8% loose, 10% each)", PS, dict(runup=0.08), 16, "4hhigh", 0.10, 1, 12, False),
        ("Marathon Mary (24h hold, 30%)",      PS, dict(), 96, "4hhigh", 0.30, 1, 4, False),
        ("Speedrun Steve (1h hold, 60% 2x)",   PS, dict(), 4, "tight", 0.60, 2, 3, False),
        ("No-Stop Nancy (30%, time exit only)", PS, dict(), 16, "none", 0.30, 1, 4, False),
        ("Wide-Boy Wes (buf2 stop, 40% 2x)",   PS, dict(), 16, "buf2", 0.40, 2, 3, False),
        ("Martingale Mike (10% base, doubles)", PS, dict(), 16, "4hhigh", 0.10, 2, 2, True),
        ("Doomer Dan (capit longs, 50%)",      sig_capit, dict(drop=0.20), 96, "none", 0.50, 1, 3, False),
        ("Deep Doomer (-25% dip, 50% 2x)",     sig_capit, dict(drop=0.25), 96, "ds15", 0.50, 2, 3, False),
        ("The Chaser (buys pumps, 50%)",       sig_chase, dict(), 16, "tight", 0.50, 1, 3, False),
        ("Kelly's Ghost (35% at 2x, strict)",  PS, dict(runup=0.16), 16, "4hhigh", 0.35, 2, 3, False),
    ]


def spark(curve, width=40):
    if len(curve) < 2:
        return " " * width
    vals = [v for _, v in curve]
    t0, t1 = curve[0][0], curve[-1][0]
    if t1 == t0:
        return " " * width
    buckets = [[] for _ in range(width)]
    for t, v in curve:
        k = min(int((t - t0) / (t1 - t0) * width), width - 1)
        buckets[k].append(v)
    pts = []
    last = vals[0]
    for b in buckets:
        if b:
            last = b[-1]
        pts.append(last)
    lo, hi = min(pts), max(pts)
    if hi == lo:
        return "▄" * width
    chars = "▁▂▃▄▅▆▇█"
    return "".join(chars[int((v - lo) / (hi - lo) * 7)] for v in pts)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    tmin = min(d["t"][0] for d in tickers.values())
    tmax = max(d["t"][-1] for d in tickers.values())
    f = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    p(f"THE DEGEN DERBY — {stamp}")
    p(f"track: {f(tmin)} -> {f(tmax)} | {len(tickers)} tickers | everyone starts ${START:,.0f}")
    p("compounding ON, liquidations ON, pre-registration left at the door")
    p("")

    results = []
    for cfg in build_field():
        name, siggen, sigkw, hold, stop, frac, lev, conc, mart = cfg
        r = race(name, tickers, siggen, sigkw, hold, stop, frac, lev, conc, mart)
        results.append(r)
        print(f"  ...{name} finished: ${r['final']:,.0f}")

    results.sort(key=lambda r: r["final"], reverse=True)
    p("=" * 110)
    p("FINAL STANDINGS")
    p("=" * 110)
    medals = ["🥇", "🥈", "🥉"] + ["  "] * 30
    for k, r in enumerate(results):
        tag = " 💀BUSTED" if r["busted"] else (f" ⚡{r['liqs']}liq" if r["liqs"] else "")
        p(f"{medals[k]} {k+1:2d}. {r['name']:42s} ${r['final']:>12,.0f}  "
          f"({r['ret']*100:+9.1f}%)  trades {r['trades']:4d}  win {r['win']*100:4.1f}%  "
          f"maxdd {r['maxdd']*100:6.1f}%{tag}")
    p("")
    p("equity sparklines (each scaled to its own range):")
    for r in results:
        p(f"  {r['name']:42s} {spark(r['curve'])}  ${r['final']:,.0f}")

    fname = f"reports/degen_derby_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
