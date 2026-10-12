#!/usr/bin/env python3
"""Test the proposed indicator/regime architecture against full-span data
(2023-01 -> 2026-10). Six experiments:

  1. Candle anatomy on the short: upper-wick >= 30% and/or close in lower
     50% of the synthetic 4h candle (O = open 16 bars ago, H/L = window
     extremes, C = current close). Rolling basis — preserves entry timing.
  2. BTC guardrail on the short: block when BTC 4h return >= +4% OR BTC
     above a rising 4h EMA20.
  3. Setup 2 momentum long: runup >= 12%, vol >= 2.5x, upper wick <= 15%,
     close in top 20%. Stop = max(window low, body midpoint) - 0.1%; 12h hold.
  4. Setup 3 panic long: 4h return <= -15%, vol >= 3x, lower wick >= 40%,
     close in upper 50%. Stop = window low - 0.1%; 8h hold.
  5. Dial statistic: self-gate on trailing 60d mean net (expectancy) vs
     trailing 60d win rate > 50%, same completed-outcome stream.
  6. Anatomy + gate stacking on the short.

Usage: python3 indicator_tests.py
Writes: reports/indicator_tests_<stamp>.txt
"""
import os
from bisect import bisect_right
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, KILL_DD, \
    KILL_LOOKBACK, KILL_PAUSE
from backtest import M15, H
from rules_backtest import TAKER, SLIP
from regime_switch_backtest import (load_full, alive, WINDOWS, DAY,
                                    pump_events, make_dial)
from regime_policy_test import self_outcomes

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def anatomy(d, i):
    """Synthetic 4h candle ending at bar i (rolling, no boundary delay)."""
    O = d["o"][i - 15] if i >= 15 else d["o"][0]
    Hh = d["h"][i - 15:i + 1].max()
    Ll = d["l"][i - 15:i + 1].min()
    C = d["c"][i]
    rng = Hh - Ll
    if rng <= 0:
        return None
    return dict(O=O, H=Hh, L=Ll, C=C,
                upwick=(Hh - max(O, C)) / rng,
                lowick=(min(O, C) - Ll) / rng,
                closeloc=(C - Ll) / rng)


def btc_guard(tickers):
    """-> fn(T) True when shorts are BLOCKED. From BTC 1h closes."""
    c1 = pd.concat([pd.read_csv("backtest/r60_oos_1h.csv.gz"),
                    pd.read_csv("backtest/r60_candles_1h.csv.gz")])
    b = c1[c1["ticker"] == "BTC"].drop_duplicates("t").sort_values("t")
    t1 = b["t"].to_numpy(np.int64) + H          # close time of each 1h bar
    c = b["c"].to_numpy(float)
    r4 = np.full(len(c), np.nan)
    r4[4:] = c[4:] / c[:-4] - 1
    b4 = b.set_index("t")["c"].groupby(lambda t: t - t % (4 * H)).last()
    e20 = b4.ewm(span=20, adjust=False).mean()
    t4 = b4.index.to_numpy() + 4 * H
    e20v = e20.to_numpy()
    px4 = b4.to_numpy()

    def blocked(T):
        i = np.searchsorted(t1, T, "right") - 1
        j = np.searchsorted(t4, T, "right") - 1
        if i < 4 or j < 1:
            return False
        above_rising = px4[j] > e20v[j] and e20v[j] > e20v[j - 1]
        return bool(r4[i] >= 0.04 or above_rising)
    return blocked


def sigs_short(tickers, t0, t1, wick=None, cloc=None):
    rows = []
    for tk, d in tickers.items():
        t, c, v = d["t"], d["c"], d["v"]
        lo, hi = np.searchsorted(t, t0 - M15), np.searchsorted(t, t1 - M15)
        for i in range(max(lo, 20), hi):
            if not alive(d, i):
                continue
            if c[i] / c[i - 16] - 1 < 0.12 or c[i] >= c[i - 1]:
                continue
            mu = v[i - 8:i].mean()
            if mu <= 0 or v[i] / mu < 2.0:
                continue
            if wick is not None or cloc is not None:
                a = anatomy(d, i)
                if a is None:
                    continue
                if wick is not None and a["upwick"] < wick:
                    continue
                if cloc is not None and a["closeloc"] > cloc:
                    continue
            stop = d["h"][i - 16:i + 1].max()
            rows.append((t[i] + M15, tk, i, -1, stop, 16))
    return rows


def sigs_long_momo(tickers, t0, t1):
    rows = []
    for tk, d in tickers.items():
        t, c, v = d["t"], d["c"], d["v"]
        lo, hi = np.searchsorted(t, t0 - M15), np.searchsorted(t, t1 - M15)
        for i in range(max(lo, 20), hi):
            if not alive(d, i):
                continue
            if c[i] / c[i - 16] - 1 < 0.12:
                continue
            mu = v[i - 8:i].mean()
            if mu <= 0 or v[i] / mu < 2.5:
                continue
            a = anatomy(d, i)
            if a is None or a["upwick"] > 0.15 or a["closeloc"] < 0.80:
                continue
            body_mid = (a["O"] + a["C"]) / 2
            stop = max(a["L"], body_mid) * 0.999
            rows.append((t[i] + M15, tk, i, 1, stop, 48))
    return rows


def sigs_long_panic(tickers, t0, t1):
    rows = []
    for tk, d in tickers.items():
        t, c, v = d["t"], d["c"], d["v"]
        lo, hi = np.searchsorted(t, t0 - M15), np.searchsorted(t, t1 - M15)
        for i in range(max(lo, 20), hi):
            if not alive(d, i):
                continue
            if c[i] / c[i - 16] - 1 > -0.15:
                continue
            mu = v[i - 8:i].mean()
            if mu <= 0 or v[i] / mu < 3.0:
                continue
            a = anatomy(d, i)
            if a is None or a["lowick"] < 0.40 or a["closeloc"] < 0.50:
                continue
            rows.append((t[i] + M15, tk, i, 1, a["L"] * 0.999, 32))
    return rows


def exit_px(d, i, entry, side, stop, hold):
    init_dist = abs(stop / entry - 1)
    for j in range(i + 1, min(i + hold + 1, len(d["t"]))):
        hit = d["h"][j] > stop if side < 0 else d["l"][j] < stop
        if hit:
            gross = side * (stop / entry - 1)
            return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", init_dist
    j = min(i + hold, len(d["t"]) - 1)
    gross = side * (d["c"][j] / entry - 1)
    return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "time", init_dist


def portfolio(sig_rows, tickers, allow=None):
    trades, pending, open_until = [], [], {}
    equity, eq_hist, kill_until = 1.0, [], 0
    for t_sig, tk, i, side, stop, hold in sorted(sig_rows):
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            equity += pnl
            eq_hist.append((et, equity))
        if allow is not None and not allow(t_sig):
            continue
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= MAX_CONC:
            continue
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and equity / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        d = tickers[tk]
        entry = d["c"][i]
        net, exit_t, kind, sl_dist = exit_px(d, i, entry, side, stop, hold)
        notional = min(RISK * equity / max(sl_dist, 0.005), NOTIONAL_CAP * equity)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades.append(dict(ticker=tk, t=t_sig, side=side, kind=kind,
                           net=net, pnl=pnl))
    for et, pnl in sorted(pending):
        equity += pnl
        eq_hist.append((et, equity))
    return trades, eq_hist


def run_arm(label, sig_fn, tickers, allow=None):
    allt, rets, dds = [], [], []
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = sig_fn(tickers, t0, t1)
        trades, eqh = portfolio(rows, tickers, allow)
        met = metrics(eqh, t0, t1)
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        allt += trades
    g = pd.DataFrame(allt) if allt else pd.DataFrame(columns=["net", "t"])
    comp = float(np.prod([1 + r for r in rets]) - 1)
    yr = {}
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        for y in (2023, 2024, 2025, 2026):
            gy = g[g["year"] == y]
            yr[y] = (gy["net"].mean() * 100, len(gy)) if len(gy) else (None, 0)
    nt = g["net"].mean() * 100 if len(g) else 0
    wr = (g["net"] > 0).mean() * 100 if len(g) else 0
    p(f"{label:28s} {len(g):5,} {nt:+9.3f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:7.1f}%  "
      + " | ".join(f"{y}: {v[0]:+.2f}%/{v[1]}" if v[1] else f"{y}: --"
                   for y, v in yr.items()))
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"INDICATOR / ARCHITECTURE TESTS — {stamp} | full span 2023-01 -> 2026-10")
    p("anatomy on SYNTHETIC rolling 4h candle (no boundary delay)")
    tickers = load_full()
    guard = btc_guard(tickers)

    hdr = (f"{'arm':28s} {'trades':>5s} {'net/trade':>10s} {'win%':>4s} "
           f"{'compound':>10s} {'worstdd':>7s}  by year")
    p("")
    p("1+2+6. SHORT: anatomy filters and BTC guard")
    p(hdr)
    run_arm("short base (ref)", lambda tk, a, b: sigs_short(tk, a, b), tickers)
    run_arm("short +wick>=30%",
            lambda tk, a, b: sigs_short(tk, a, b, wick=0.30), tickers)
    run_arm("short +closeloc<=50%",
            lambda tk, a, b: sigs_short(tk, a, b, cloc=0.50), tickers)
    run_arm("short +wick+closeloc",
            lambda tk, a, b: sigs_short(tk, a, b, wick=0.30, cloc=0.50), tickers)
    run_arm("short +BTC-guard",
            lambda tk, a, b: sigs_short(tk, a, b), tickers,
            allow=lambda T: not guard(T))

    # gate (30d broad-pump dial) stacking
    ev_t, ev_r, ev_done = pump_events(tickers)
    d30 = make_dial(ev_t, ev_r, ev_done, 30, 0.0)
    gate_ok = lambda T: d30(T)[0] == -1
    run_arm("short +gate30 (deployed)",
            lambda tk, a, b: sigs_short(tk, a, b), tickers, allow=gate_ok)
    run_arm("short +anatomy +gate30",
            lambda tk, a, b: sigs_short(tk, a, b, wick=0.30, cloc=0.50),
            tickers, allow=gate_ok)

    p("")
    p("3+4. PROPOSED LONG SETUPS")
    p(hdr)
    run_arm("momo long (setup 2)", sigs_long_momo, tickers)
    run_arm("panic long (setup 3)", sigs_long_panic, tickers)

    p("")
    p("5. DIAL STATISTIC — self-gate stream, expectancy vs win-rate")
    all_sigs = []
    for wname, a, b in WINDOWS:
        rows = sigs_short(tickers, ts(a), ts(b))
        all_sigs += [(r[0], r[1], r[2]) for r in rows]
    st_, sn_, sd_ = self_outcomes(tickers, all_sigs)

    def self_stat(window_days, use_winrate):
        def ok(T):
            hi = bisect_right(sd_, T)
            if hi == 0:
                return False
            mask = st_[:hi] >= T - window_days * DAY
            if mask.sum() < 8:
                return False
            x = sn_[:hi][mask]
            return (x > 0).mean() > 0.50 if use_winrate else x.mean() > 0
        return ok
    p(hdr)
    run_arm("selfgate 60d expectancy",
            lambda tk, a, b: sigs_short(tk, a, b), tickers,
            allow=self_stat(60, False))
    run_arm("selfgate 60d winrate>50%",
            lambda tk, a, b: sigs_short(tk, a, b), tickers,
            allow=self_stat(60, True))

    p("")
    p("NOTES: all entries at 15m close (rolling window) — the proposed 4h")
    p("candle-boundary execution adds up to 3h45m delay; the delay ladder")
    p("already showed 1h delay erases the short edge. postOnly fills not")
    p("modeled (costs x4 already survived; fill-risk > fee savings here).")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/indicator_tests_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
