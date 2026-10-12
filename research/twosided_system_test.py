#!/usr/bin/env python3
"""The two-sided regime system: each regime gets its own anatomically-correct
entry, the dial picks which book is open.

  dial < 0 (pumps fading)     -> exhaustion SHORT (weak-close entry)
  dial > 0 (pumps continuing) -> momentum LONG (strong-close entry, setup 2)
  n < 10 events               -> flat

Arms over 2023-01 -> 2026-10, quarterly windows:
  A  short-only base               (fleet anchor)
  B  short-only +wick30            (anatomy upgrade, ungated)
  C  gate30 short                  (deployed variant)
  D  two-sided 30d                 (short base / momo long)
  E  two-sided 60d
  F  two-sided 30d, wick30 short
  G  momo-long only when dial>0    (the long book alone)

Usage: python3 twosided_system_test.py
Writes: reports/twosided_system_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from regime_switch_backtest import load_full, pump_events, make_dial, WINDOWS
from indicator_tests import sigs_short, sigs_long_momo, portfolio

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def run(label, sig_builder, tickers):
    allt, rets, dds = [], [], []
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = sig_builder(t0, t1)
        trades, eqh = portfolio(rows, tickers)
        met = metrics(eqh, t0, t1)
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        allt += trades
    g = pd.DataFrame(allt) if allt else pd.DataFrame(columns=["net", "t", "side"])
    comp = float(np.prod([1 + r for r in rets]) - 1)
    nt = g["net"].mean() * 100 if len(g) else 0
    wr = (g["net"] > 0).mean() * 100 if len(g) else 0
    posy = ""
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        parts = []
        for y in (2023, 2024, 2025, 2026):
            gy = g[g["year"] == y]
            parts.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy)}"
                         if len(gy) else f"{y}: --")
        posy = " | ".join(parts)
    p(f"{label:26s} {len(g):5,} {nt:+9.3f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:7.1f}%  {posy}")
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"TWO-SIDED REGIME SYSTEM — {stamp} | 2023-01 -> 2026-10")
    tickers = load_full()
    ev_t, ev_r, ev_done = pump_events(tickers)
    d30 = make_dial(ev_t, ev_r, ev_done, 30, 0.0)
    d60 = make_dial(ev_t, ev_r, ev_done, 60, 0.0)

    def twosided(dial, t0, t1, wick=None):
        shorts = [r for r in sigs_short(tickers, t0, t1, wick=wick)
                  if dial(r[0])[0] == -1]
        longs = [r for r in sigs_long_momo(tickers, t0, t1)
                 if dial(r[0])[0] == 1]
        return shorts + longs

    p("")
    p(f"{'arm':26s} {'trades':>5s} {'net/trade':>10s} {'win%':>4s} "
      f"{'compound':>10s} {'worstdd':>7s}  by year")
    run("A short base",
        lambda a, b: sigs_short(tickers, a, b), tickers)
    run("B short +wick30",
        lambda a, b: sigs_short(tickers, a, b, wick=0.30), tickers)
    run("C gate30 short (deployed)",
        lambda a, b: [r for r in sigs_short(tickers, a, b)
                      if d30(r[0])[0] == -1], tickers)
    g = run("D two-sided 30d",
            lambda a, b: twosided(d30, a, b), tickers)
    run("E two-sided 60d",
        lambda a, b: twosided(d60, a, b), tickers)
    run("F two-sided 30d wick30",
        lambda a, b: twosided(d30, a, b, wick=0.30), tickers)
    run("G momo long, dial>0 only",
        lambda a, b: [r for r in sigs_long_momo(tickers, a, b)
                      if d30(r[0])[0] == 1], tickers)

    if len(g):
        p("")
        p("arm D decomposition by side:")
        for s, lbl in ((-1, "shorts"), (1, "longs")):
            gs = g[g["side"] == s]
            if len(gs):
                p(f"  {lbl:6s}: {len(gs):4,} trades | net/trade "
                  f"{gs['net'].mean()*100:+.3f}% | win {(gs['net']>0).mean()*100:.0f}%")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/twosided_system_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
