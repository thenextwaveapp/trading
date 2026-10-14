#!/usr/bin/env python3
"""Portfolio-level comparison of loser-engine exits: compounded equity,
drawdown, not per-trade means.

Fleet-style sim: 12 slots, notional = equity/12 at entry, one entry per
hour (biggest 1h loser <= -2%), re-entry allowed, exits per variant on
15m closes. Faster exits free slots sooner -> more trades; that effect
is included.

Usage: PYTHONPATH=research python3 research/loser_equity_curves.py
Writes: reports/loser_equity_curves_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST
from hourly_explore import precompute, build_panel, H_MS

SLOTS = 12

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def path_exit(d, i, hold, ex):
    """-> (net, bars_held) on 15m closes, None on gap."""
    t, c = d["t"], d["c"]
    j = i + hold
    if j >= len(t) or t[j] - t[i] != hold * M15:
        return None
    entry = c[i]
    r = c[i + 1:j + 1] / entry - 1
    kind = ex["kind"]
    if kind == "time":
        return r[-1] - COST, hold
    if kind == "partial":
        tp_hit = r >= ex["x"]
        k = int(np.argmax(tp_hit))
        if tp_hit[k]:
            # half exits at tp, half at time; held full duration
            return 0.5 * (r[k] - COST) + 0.5 * (r[-1] - COST), hold
        return r[-1] - COST, hold
    if kind == "sl":
        hit = r <= -ex["x"]
    elif kind == "tp":
        hit = r >= ex["x"]
    elif kind == "trail":
        peak = np.maximum.accumulate(r)
        hit = (peak >= ex["arm"]) & ((1 + r) <= (1 + peak) * (1 - ex["w"]))
    else:
        raise ValueError(kind)
    k = int(np.argmax(hit))
    if hit[k]:
        return r[k] - COST, k + 1
    return r[-1] - COST, hold


def simulate(grid, tks, panel, tickers, ex, thr=0.02, hold=96):
    """Compounded fleet sim. Returns daily equity series."""
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    equity = 1.0
    open_pos = []            # list of (exit_time_ms, pnl_abs)
    eq_t, eq_v = [], []
    for r in range(len(grid)):
        T = grid[r]
        # settle exits
        still = []
        for xt, pnl in open_pos:
            if xt <= T:
                equity += pnl
            else:
                still.append((xt, pnl))
        open_pos = still
        row = r1m[r]
        if not np.all(np.isnan(row)):
            j = int(np.nanargmin(row))
            if row[j] <= -thr and len(open_pos) < SLOTS:
                d = tickers[tks[j]]
                i = panel["idx"][r, j]
                res = path_exit(d, i, hold, ex)
                if res is not None:
                    net, bars = res
                    notional = equity / SLOTS
                    open_pos.append((T + bars * M15, notional * net))
        eq_t.append(T)
        eq_v.append(equity + sum(pnl for _, pnl in open_pos if False))
    s = pd.Series(eq_v, index=pd.to_datetime(eq_t, unit="ms"))
    return s.resample("1D").last().dropna()


def stats(label, s):
    ret = s.iloc[-1] / s.iloc[0] - 1
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    cagr = (1 + ret) ** (1 / yrs) - 1
    dd = (s / s.cummax() - 1)
    mdd = dd.min()
    daily = s.pct_change().dropna()
    worst = daily.min()
    sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else 0
    s26 = s[s.index >= "2026-01-01"]
    r26 = s26.iloc[-1] / s26.iloc[0] - 1 if len(s26) > 1 else float("nan")
    dd26 = (s26 / s26.cummax() - 1).min() if len(s26) > 1 else float("nan")
    p(f"{label:28s} total {ret*100:+8.1f}%  cagr {cagr*100:+6.1f}%  "
      f"maxDD {mdd*100:6.1f}%  mar {cagr/abs(mdd):5.2f}  "
      f"sharpe {sharpe:4.2f}  worstday {worst*100:5.1f}%  "
      f"2026 {r26*100:+6.1f}% dd {dd26*100:5.1f}%")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    p(f"LOSER EQUITY CURVES — {stamp}")
    p(f"12 slots, equity/12 per entry, compounded, thr 2%, cost {COST*100:.2f}%")
    p("")
    for label, ex, hold in [
        ("time 24h (baseline)", {"kind": "time"}, 96),
        ("time 6h",             {"kind": "time"}, 24),
        ("time 2h",             {"kind": "time"}, 8),
        ("tp +5%",              {"kind": "tp", "x": 0.05}, 96),
        ("partial half tp+4%",  {"kind": "partial", "x": 0.04}, 96),
        ("trail arm+3% w3%",    {"kind": "trail", "arm": 0.03, "w": 0.03}, 96),
        ("stop -8%",            {"kind": "sl", "x": 0.08}, 96),
    ]:
        stats(label, simulate(grid, tks, panel, tickers, ex, hold=hold))
    p("")
    os.makedirs("reports", exist_ok=True)
    out = f"reports/loser_equity_curves_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt"
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
