#!/usr/bin/env python3
"""Capitulation-long FLEET VARIANTS backtest.

Base strategy (picked 2026-10-10 from mined Invo long data):
  24h return <= -20% (fresh crossing) AND BTC bear (4h EMA20 < EMA50)
  -> LONG at 15m close, NO stop, time exit 96c (24h). Sizing basis 2*natr.

Variant axes (fleet-style, one knob at a time + a few combos):
  gate      : bear-gated (base) / ungated / bull-only (control)
  depth     : -15 / -20 / -25 / -30%
  hold      : 32c / 48c / 96c / 192c
  confirm   : +green close / +vol>=2x / +natr-high
  exits     : disaster stop -15% / -25%; take-profit +5 / +10 / +20%
              (TP first-touch intrabar, time exit fallback)
  combos    : deep -25% bear / bear+green / bear+vol2 / slow 192 bear /
              fast 32 bear

Usage: python3 capit_variants_backtest.py
Writes: reports/capit_variants_<stamp>.txt, backtest/trades_capitvariants.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from regime_switch_backtest import load_full, WINDOWS
from long_search import COST, YEARS
from long_robustness import portfolio, btc_regime
from long_rules_backtest import precompute2, gen_signals

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def make_exit(hold=96, dstop=None, tp=None):
    """dstop = disaster stop fraction below entry; tp = take-profit fraction
    above entry (first touch intrabar). Time exit fallback."""
    def exit_fn(d, i):
        t, h, l, c = d["t"], d["h"], d["l"], d["c"]
        entry = c[i]
        natr = d["natr_v"][i]
        sl_dist = max(2 * natr if natr == natr else 0.02, 0.005)
        sl_level = entry * (1 - dstop) if dstop else -np.inf
        tp_level = entry * (1 + tp) if tp else np.inf
        for j in range(i + 1, min(i + hold + 1, len(t))):
            # conservative: check stop before TP within the same bar
            if l[j] < sl_level:
                return (sl_level / entry - 1) - COST, t[j] + M15, "sl", sl_dist
            if h[j] > tp_level:
                return (tp_level / entry - 1) - COST, t[j] + M15, "tp", sl_dist
        j = min(i + hold, len(t) - 1)
        return (c[j] / entry - 1) - COST, t[j] + M15, "time", sl_dist
    return exit_fn


def run_variant(tickers, label, store, gate=None, depth=0.20, hold=96,
                dstop=None, tp=None, **sig_kw):
    exit_fn = make_exit(hold, dstop, tp)
    allt, rets, dds = [], [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i)
                     for tsg, i in gen_signals(d, t0, t1, trig="r24",
                                               depth=depth, **sig_kw)]
        if gate:
            rows = [r for r in rows if gate(r[0])]
        trades, eqh = portfolio(rows, tickers, exit_fn)
        met = metrics(eqh, t0, t1)
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        for x in trades:
            x.update(window=name)
        allt += trades
    g = pd.DataFrame(allt) if allt else pd.DataFrame(
        columns=["net", "t", "kind", "ticker"])
    comp = float(np.prod([1 + r for r in rets]) - 1)
    nt = g["net"].mean() * 100 if len(g) else 0
    md = g["net"].median() * 100 if len(g) else 0
    wr = (g["net"] > 0).mean() * 100 if len(g) else 0
    posy = []
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        for y in YEARS:
            gy = g[g["year"] == y]
            posy.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy)}"
                        if len(gy) else f"{y}: --")
    yrs_pos = sum(1 for y in YEARS if len(g) and
                  len(g[g["year"] == y]) and g[g["year"] == y]["net"].mean() > 0)
    p(f"{label:30s} {len(g):5,} {nt:+8.3f}% {md:+7.2f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:6.1f}% {yrs_pos}/4  "
      + " | ".join(posy))
    if len(g):
        g["variant"] = label
        store.append(g)
    return dict(variant=label, trades=len(g), net=nt, median=md, win=wr,
                comp=comp * 100, dd=min(dds) * 100, yrs_pos=yrs_pos)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute2(d)
    bull = btc_regime(tickers)
    bear = lambda T: not bull(T)
    p(f"CAPITULATION-LONG FLEET VARIANTS — {stamp} | {len(tickers)} tickers "
      "| full span 2023-01 -> 2026-10")
    p("base = 24h ret <= -20% fresh crossing + BTC bear (4h EMA20<EMA50) -> "
      "long at close, no stop, hold 96c")
    p("")
    hdr = (f"{'variant':30s} {'trades':>5s} {'net/tr':>8s} {'median':>7s} "
           f"{'win%':>4s} {'comp':>9s} {'dd':>6s} {'y+':>3s}  by year")
    store, summ = [], []

    p("1. GATE")
    p(hdr)
    summ.append(run_variant(tickers, "BASE bear -20% h96", store, gate=bear))
    summ.append(run_variant(tickers, "ungated", store))
    summ.append(run_variant(tickers, "bull-only (control)", store,
                            gate=lambda T: bull(T)))

    p("")
    p("2. DEPTH (bear-gated)")
    p(hdr)
    for dep in (0.15, 0.25, 0.30):
        summ.append(run_variant(tickers, f"depth -{dep:.0%}", store,
                                gate=bear, depth=dep))

    p("")
    p("3. HOLD (bear-gated)")
    p(hdr)
    for hold in (32, 48, 192):
        summ.append(run_variant(tickers, f"hold {hold}c ({hold//4}h)", store,
                                gate=bear, hold=hold))

    p("")
    p("4. CONFIRMATION FILTERS (bear-gated)")
    p(hdr)
    summ.append(run_variant(tickers, "+green close", store, gate=bear,
                            green=True))
    summ.append(run_variant(tickers, "+vol>=2x", store, gate=bear, volx=2.0))
    summ.append(run_variant(tickers, "+natr-high", store, gate=bear,
                            natr_hi=True))

    p("")
    p("5. EXITS (bear-gated): disaster stops and take-profits")
    p(hdr)
    summ.append(run_variant(tickers, "dstop -15%", store, gate=bear,
                            dstop=0.15))
    summ.append(run_variant(tickers, "dstop -25%", store, gate=bear,
                            dstop=0.25))
    summ.append(run_variant(tickers, "tp +5%", store, gate=bear, tp=0.05))
    summ.append(run_variant(tickers, "tp +10%", store, gate=bear, tp=0.10))
    summ.append(run_variant(tickers, "tp +20%", store, gate=bear, tp=0.20))
    summ.append(run_variant(tickers, "tp +10% dstop -15%", store, gate=bear,
                            tp=0.10, dstop=0.15))

    p("")
    p("6. COMBOS")
    p(hdr)
    summ.append(run_variant(tickers, "deep -25% bear", store, gate=bear,
                            depth=0.25))
    summ.append(run_variant(tickers, "bear +green", store, gate=bear,
                            green=True))
    summ.append(run_variant(tickers, "slow: 192c bear", store, gate=bear,
                            hold=192))
    summ.append(run_variant(tickers, "fast: 32c bear", store, gate=bear,
                            hold=32))
    summ.append(run_variant(tickers, "slow deep: -25% 192c bear", store,
                            gate=bear, depth=0.25, hold=192))

    p("")
    p("=" * 100)
    p("RANKED (by net/trade, min 50 trades, all-4-years-positive flagged)")
    s = pd.DataFrame(summ)
    s = s[s["trades"] >= 50].sort_values("net", ascending=False)
    for _, r in s.iterrows():
        flag = " ****" if r["yrs_pos"] == 4 else ""
        p(f"  {r['variant']:30s} {r['net']:+7.3f}%/tr x{r['trades']:4,} | "
          f"win {r['win']:3.0f}% | comp {r['comp']:+9.2f}% | dd "
          f"{r['dd']:5.1f}% | years+ {r['yrs_pos']}/4{flag}")

    if store:
        t = pd.concat(store)
        t.to_csv("backtest/trades_capitvariants.csv.gz", index=False,
                 compression="gzip")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/capit_variants_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
