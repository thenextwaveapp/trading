#!/usr/bin/env python3
"""Risk management for the loser engine: where is the no-recovery
point, does a stop help once TP harvesting is on, and is there any
value holding past 24h?

A. recoverability: once a trade touches -X%, P(ends >0) and E[final]
B. per-trade grid: tp {8,10} x sl {none,-8,-10,-15} x hold {24,48,72h}
C. compounded growth for the leaders

Usage: PYTHONPATH=research python3 research/loser_stop_risk.py
Writes: reports/loser_stop_risk_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from regime_switch_backtest import load_full
from long_search import COST, YEARS
from hourly_explore import precompute, build_panel
import loser_equity_curves as lec

BARS = 288                                   # 72h of 15m closes

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def collect_paths(grid, tks, panel, tickers):
    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    paths, ts = [], []
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        j = int(np.nanargmin(row))
        if row[j] > -0.02:
            continue
        d = tickers[tks[j]]
        i = panel["idx"][r, j]
        t, c = d["t"], d["c"]
        k = i + BARS
        if k >= len(t) or t[k] - t[i] != BARS * M15:
            continue
        paths.append(c[i + 1:k + 1] / c[i] - 1)
        ts.append(grid[r])
    return np.vstack(paths), np.asarray(ts)


def policy(R, H, tp=None, sl=None):
    """Exit at first tp/sl close within H bars, else time H. -> net."""
    n = len(R)
    first_tp = np.full(n, H)
    first_sl = np.full(n, H)
    if tp is not None:
        hit = R[:, :H] >= tp
        has = hit.any(axis=1)
        first_tp = np.where(has, np.argmax(hit, axis=1), H)
    if sl is not None:
        hit = R[:, :H] <= -sl
        has = hit.any(axis=1)
        first_sl = np.where(has, np.argmax(hit, axis=1), H)
    k = np.minimum(np.minimum(first_tp, first_sl), H - 1)
    out = R[np.arange(n), k]
    out = np.where((sl is not None) & (first_sl < first_tp) & (first_sl < H),
                   -sl if sl is not None else out, out)
    out = np.where((tp is not None) & (first_tp <= first_sl) & (first_tp < H),
                   tp if tp is not None else out, out)
    return out - COST


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    R, ts = collect_paths(grid, tks, panel, tickers)
    year = pd.to_datetime(pd.Series(ts), unit="ms").dt.year.to_numpy()
    p(f"LOSER STOP / RISK — {stamp}")
    p(f"{len(R):,} trades with full 72h paths, cost {COST*100:.2f}%")
    p("")

    p("A. RECOVERABILITY (within 24h window)")
    p(f"{'touched':>9} {'% trades':>9} {'P(final24>0)':>13} "
      f"{'E[final24]':>11} {'E[final72]':>11}")
    f24, f72 = R[:, 95], R[:, -1]
    for x in (0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        m = (R[:, :96] <= -x).any(axis=1)
        if m.sum() == 0:
            continue
        p(f"{-x*100:8.0f}% {m.mean()*100:8.1f}% "
          f"{(f24[m]>0).mean()*100:12.0f}% {f24[m].mean()*100:+10.2f}% "
          f"{f72[m].mean()*100:+10.2f}%")
    p("")

    p("B. POLICY GRID (mean net %/trade | 2026 only)")
    hdr = f"{'policy':28s}" + "".join(f"{f'{h//4}h':>14}" for h in (96, 192, 288))
    p(hdr)
    for tp in (0.08, 0.10, None):
        for sl in (None, 0.08, 0.10, 0.15):
            cells = []
            for H in (96, 192, 288):
                net = policy(R, H, tp, sl)
                cells.append(f"{net.mean()*100:+6.3f}|{net[year==2026].mean()*100:+6.3f}")
            tpl = f"tp{tp*100:.0f}" if tp else "hold"
            sll = f" sl-{sl*100:.0f}" if sl else " nosl"
            p(f"{tpl+sll:28s}" + "".join(f"{c:>14}" for c in cells))
    p("")

    p("C. COMPOUNDED (12 slots), leaders + reference")
    orig = lec.path_exit
    def patched(d, i, hold, ex):
        if ex["kind"] != "tpsl":
            return orig(d, i, hold, ex)
        t, c = d["t"], d["c"]
        j = i + hold
        if j >= len(t) or t[j] - t[i] != hold * M15:
            return None
        r = c[i + 1:j + 1] / c[i] - 1
        tp_hit = r >= ex["x"]
        sl_hit = r <= -ex["s"]
        ktp = int(np.argmax(tp_hit)) if tp_hit.any() else hold
        ksl = int(np.argmax(sl_hit)) if sl_hit.any() else hold
        if ktp == hold and ksl == hold:
            return r[-1] - COST, hold
        if ktp <= ksl:
            return ex["x"] - COST, ktp + 1
        return -ex["s"] - COST, ksl + 1
    lec.path_exit = patched
    def stats(label, s):
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
        mdd = (s / s.cummax() - 1).min()
        s26 = s[s.index >= "2026-01-01"]
        r26 = s26.iloc[-1] / s26.iloc[0] - 1
        dd26 = (s26 / s26.cummax() - 1).min()
        p(f"{label:22s} cagr {cagr*100:+7.1f}%  maxDD {mdd*100:6.1f}%  "
          f"mar {cagr/abs(mdd):5.2f}  2026 {r26*100:+6.1f}% dd {dd26*100:6.1f}%")
    for label, ex, hold in (
        ("tp10 (ref)", {"kind": "tp", "x": 0.10}, 96),
        ("tp10 sl-10 24h", {"kind": "tpsl", "x": 0.10, "s": 0.10}, 96),
        ("tp10 sl-15 24h", {"kind": "tpsl", "x": 0.10, "s": 0.15}, 96),
        ("tp10 sl-15 48h", {"kind": "tpsl", "x": 0.10, "s": 0.15}, 192),
        ("tp8 sl-10 24h", {"kind": "tpsl", "x": 0.08, "s": 0.10}, 96),
    ):
        stats(label, lec.simulate(grid, tks, panel, tickers, ex, hold=hold))
    lec.path_exit = orig
    p("")
    os.makedirs("reports", exist_ok=True)
    out = f"reports/loser_stop_risk_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt"
    with open(out, "w") as f:
        f.write("\n".join(OUT) + "\n")
    p(f"wrote {out}")


if __name__ == "__main__":
    main()
