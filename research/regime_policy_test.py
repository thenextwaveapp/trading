#!/usr/bin/env python3
"""Policy layer on top of regime_switch_backtest: which USE of the dial makes
money — flip, gate (short/flat), or self-referential gate?

Arms (full span 2023-01 -> 2026-10, same signal/fees/sizing):
  short-only           baseline, what the fleet runs
  flip-30 / flip-60    switch direction by broad-pump dial (from run 1)
  gate-30 / gate-60    short when dial says SHORT, else FLAT (no longs)
  selfgate-60/90       short when the trailing mean net of the strategy's own
                       completed hypothetical shorts > 0, else flat.
                       (every signal is simulated as a short regardless of
                       whether it was taken; outcome usable after exit time)
  selfflip-60/90       same dial, but go LONG when trailing net < 0

Usage: python3 regime_policy_test.py
Writes: reports/regime_policy_<stamp>.txt
"""
import os
from bisect import bisect_right
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from regime_switch_backtest import (load_full, pump_events, make_dial,
                                    signals, exit_trade, portfolio, WINDOWS,
                                    MIN_EV, DAY)

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def self_outcomes(tickers, all_sigs):
    """Hypothetical short outcome of EVERY signal (taken or not).
    Returns arrays sorted by completion time: (sig_t, net, done_t)."""
    rows = []
    for t_sig, tk, i in all_sigs:
        d = tickers[tk]
        net, exit_t, _, _ = exit_trade(d, i, d["c"][i], -1)
        rows.append((t_sig, net, exit_t))
    rows.sort(key=lambda r: r[2])
    return (np.array([r[0] for r in rows]),
            np.array([r[1] for r in rows]),
            np.array([r[2] for r in rows]))


def make_self_dial(st, sn, sd, window_days, min_ev=8):
    def dial(T):
        hi = bisect_right(sd, T)
        if hi == 0:
            return 0
        mask = st[:hi] >= T - window_days * DAY
        if mask.sum() < min_ev:
            return 0
        return 1 if float(sn[:hi][mask].mean()) > 0 else -1
    return dial


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"REGIME POLICY TEST — {stamp} | full span 2023-01 -> 2026-10")
    tickers = load_full()
    ev_t, ev_r, ev_done = pump_events(tickers)

    sig_by_win, all_sigs = {}, []
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i) for tsg, i in signals(d, t0, t1)]
        sig_by_win[wname] = (rows, t0, t1)
        all_sigs += rows

    st, sn, sd = self_outcomes(tickers, all_sigs)
    p(f"signals total: {len(all_sigs)} | broad pump events: {len(ev_t):,}")

    d30 = make_dial(ev_t, ev_r, ev_done, 30, 0.0)
    d60 = make_dial(ev_t, ev_r, ev_done, 60, 0.0)
    s60 = make_self_dial(st, sn, sd, 60)
    s90 = make_self_dial(st, sn, sd, 90)

    arms = {
        "short-only":  lambda T: -1,
        "flip-30":     lambda T: d30(T)[0],
        "flip-60":     lambda T: d60(T)[0],
        "gate-30":     lambda T: -1 if d30(T)[0] == -1 else 0,
        "gate-60":     lambda T: -1 if d60(T)[0] == -1 else 0,
        "selfgate-60": lambda T: -1 if s60(T) == 1 else 0,
        "selfgate-90": lambda T: -1 if s90(T) == 1 else 0,
        "selfflip-60": lambda T: -1 if s60(T) == 1 else (1 if s60(T) == -1 else 0),
        "selfflip-90": lambda T: -1 if s90(T) == 1 else (1 if s90(T) == -1 else 0),
    }

    store, win_stats = [], {k: [] for k in arms}
    for wname, a, b in WINDOWS:
        rows, t0, t1 = sig_by_win[wname]
        for arm, fn in arms.items():
            trades, eqh, nskip = portfolio(rows, tickers, fn)
            met = metrics(eqh, t0, t1)
            nets = [x["net"] for x in trades]
            for x in trades:
                x.update(window=wname, arm=arm)
            store += trades
            win_stats[arm].append(dict(window=wname, n=len(trades),
                                       net=np.mean(nets) if nets else np.nan,
                                       ret=met["ret"], dd=met["maxdd"]))

    t = pd.DataFrame(store)
    t["year"] = pd.to_datetime(t["t"], unit="ms").dt.year

    p("")
    p("FULL-SPAN SUMMARY")
    p(f"{'arm':12s} {'trades':>6s} {'net/trade':>10s} {'win%':>5s} "
      f"{'compounded':>10s} {'worst dd':>8s} {'sharpe-ish':>10s}")
    for arm in arms:
        g = t[t["arm"] == arm]
        ws = pd.DataFrame(win_stats[arm])
        comp = (1 + ws["ret"]).prod() - 1
        rets = ws["ret"].to_numpy()
        sh = rets.mean() / rets.std() * 2 if rets.std() > 0 else np.nan
        if not len(g):
            p(f"{arm:12s}      0")
            continue
        p(f"{arm:12s} {len(g):6,} {g['net'].mean()*100:+9.3f}% "
          f"{(g['net']>0).mean()*100:4.0f}% {comp*100:+9.2f}% "
          f"{ws['dd'].min()*100:7.1f}% {sh:9.2f}")

    p("")
    p("BY YEAR (net/trade % / trades)")
    for arm in arms:
        g = t[t["arm"] == arm]
        parts = []
        for y in (2023, 2024, 2025, 2026):
            gy = g[g["year"] == y]
            parts.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy):3,}"
                         if len(gy) else f"{y}:    --   ")
        p(f"  {arm:12s} " + " | ".join(parts))

    # equity curve per quarter for the top arms
    p("")
    p("QUARTERLY EQUITY (%) — short-only vs gate-30 vs selfgate-60")
    p(f"{'win':7s} {'short-only':>11s} {'gate-30':>9s} {'selfgate-60':>12s}")
    for k in range(len(WINDOWS)):
        wn = WINDOWS[k][0]
        vals = []
        for arm in ("short-only", "gate-30", "selfgate-60"):
            vals.append(win_stats[arm][k]["ret"] * 100)
        p(f"{wn:7s} {vals[0]:+10.2f}% {vals[1]:+8.2f}% {vals[2]:+11.2f}%")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/regime_policy_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
