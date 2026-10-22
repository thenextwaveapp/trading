#!/usr/bin/env python3
"""Capitulation-long robustness battery.

Candidate from the DATA-MINED long family (long_miner.py -> long_rules_
backtest.py): 24h return <= -20% on fresh crossing -> LONG at 15m close,
NO stop (stops demonstrably destroy the trade: 71-87%% stop-outs), time
exit after 96 bars (24h). Sizing basis 2*natr (same as rules backtest).

Battery:
  A. neighborhood (depth x hold) — is -20%/96 a ridge or a lucky point?
  B. perishability + cost stress
  C. bootstrap CI
  D. leave-one-out (years, tickers, winners) + tail stats
  E. random-long placebo matched per window
  F. BTC regime split
  G. CRASH-DAY CLUSTERING — the real risk: one crash day fires many
     tickers at once; measure per-day concentration and concurrency
  H. head-to-head vs the mirror rule (context line)

Usage: python3 capit_long_robustness.py
Writes: reports/capit_long_robustness_<stamp>.txt
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from regime_switch_backtest import load_full, WINDOWS
from long_search import COST, YEARS
from long_robustness import portfolio, placebo, btc_regime
from long_rules_backtest import precompute2, gen_signals

DAY = 86_400_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def make_exit(hold=96, cost_mult=1.0, delay=0, next_open=False):
    cost = COST * cost_mult

    def exit_fn(d, i):
        t, o, c = d["t"], d["o"], d["c"]
        natr = d["natr_v"][i]
        sl_dist = max(2 * natr if natr == natr else 0.02, 0.005)
        if next_open:
            if i + 1 >= len(t):
                return None
            entry, start = o[i + 1], i + 1
        elif delay:
            if i + delay >= len(t):
                return None
            entry, start = c[i + delay], i + delay
        else:
            entry, start = c[i], i
        j = min(start + hold, len(t) - 1)
        return (c[j] / entry - 1) - cost, t[j] + M15, "time", sl_dist

    return exit_fn


def run_variant(tickers, label, depth=0.20, hold=96, cost_mult=1.0,
                delay=0, next_open=False):
    exit_fn = make_exit(hold, cost_mult, delay, next_open)
    all_trades, rets, dds = [], [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i)
                     for tsg, i in gen_signals(d, t0, t1, trig="r24",
                                               depth=depth)]
        trades, eqh = portfolio(rows, tickers, exit_fn)
        met = metrics(eqh, t0, t1)
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        for x in trades:
            x.update(window=name)
        all_trades += trades
    g = pd.DataFrame(all_trades) if all_trades else pd.DataFrame(
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
    p(f"{label:34s} {len(g):5,} {nt:+8.3f}% {md:+8.3f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:6.1f}%  " + " | ".join(posy))
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute2(d)
    p(f"CAPITULATION-LONG ROBUSTNESS — {stamp} | {len(tickers)} tickers | "
      "full span 2023-01 -> 2026-10")
    p("candidate = 24h ret <= -20% fresh crossing -> LONG at close, "
      "NO stop, time exit 96c (24h)")
    p("")
    hdr = (f"{'variant':34s} {'trades':>5s} {'net/tr':>8s} {'median':>8s} "
           f"{'win%':>4s} {'comp':>9s} {'dd':>6s}  by year")

    p("-" * 78)
    p("A. NEIGHBORHOOD (depth x hold) — ridge or lucky point?")
    p(hdr)
    base = run_variant(tickers, "BASELINE -20% h96")
    for dep in (0.15, 0.18, 0.22, 0.25, 0.30):
        run_variant(tickers, f"depth -{dep:.0%}", depth=dep)
    for hold in (32, 64, 144, 192):
        run_variant(tickers, f"hold {hold}c ({hold//4}h)", hold=hold)

    p("")
    p("-" * 78)
    p("B. PERISHABILITY + COST STRESS")
    p(hdr)
    run_variant(tickers, "entry next open", next_open=True)
    run_variant(tickers, "entry +2 bars (30m)", delay=2)
    run_variant(tickers, "entry +4 bars (1h)", delay=4)
    run_variant(tickers, "entry +16 bars (4h)", delay=16)
    run_variant(tickers, "costs x2", cost_mult=2.0)
    run_variant(tickers, "costs x4", cost_mult=4.0)

    bt = base.copy()
    nets = bt["net"].to_numpy()
    rng = np.random.default_rng(7)

    p("")
    p("-" * 78)
    p("C. BOOTSTRAP CI (10,000 resamples)")
    bs = np.array([rng.choice(nets, len(nets)).mean() for _ in range(10_000)])
    p(f"pooled {nets.mean()*100:+.3f}% | 95% CI "
      f"[{np.percentile(bs,2.5)*100:+.3f}%, {np.percentile(bs,97.5)*100:+.3f}%]"
      f" | P(mean<=0) = {(bs <= 0).mean()*100:.2f}%")

    p("")
    p("D. LEAVE-ONE-OUT + TAILS")
    bt["year"] = pd.to_datetime(bt["t"], unit="ms").dt.year
    for y in YEARS:
        sub = bt[bt["year"] != y]["net"]
        iny = bt[bt["year"] == y]["net"]
        p(f"  drop {y}: {len(sub):4d} trades net {sub.mean()*100:+.3f}% "
          f"(year alone {iny.mean()*100 if len(iny) else 0:+.3f}%/{len(iny)})")
    for tk in bt.groupby("ticker")["pnl"].sum().abs() \
                .sort_values(ascending=False).head(5).index:
        sub = bt[bt["ticker"] != tk]["net"]
        p(f"  drop {tk:10s}: net {sub.mean()*100:+.3f}%")
    srt = np.sort(nets)
    p(f"  drop top-5 winners {srt[:-5].mean()*100:+.3f}% | top-10 "
      f"{srt[:-10].mean()*100:+.3f}% | top-20 {srt[:-20].mean()*100:+.3f}%")
    p(f"  max single loss {srt[0]*100:+.2f}% | p5 {np.percentile(nets,5)*100:+.2f}% "
      f"| p95 {np.percentile(nets,95)*100:+.2f}% | max win {srt[-1]*100:+.2f}%")

    p("")
    p("E. RANDOM-LONG PLACEBO (matched counts/window, 200 reps, 16c hold "
      "proxy for beta)")
    counts = bt.groupby("window").size().to_dict()
    pl = placebo(tickers, counts, 200, rng)
    p(f"placebo mean {pl.mean()*100:+.3f}%, 95th pct "
      f"{np.percentile(pl,95)*100:+.3f}% | actual {nets.mean()*100:+.3f}% "
      f"beats {(pl < nets.mean()).mean()*100:.1f}% of runs")

    p("")
    p("F. BTC REGIME SPLIT")
    bull = btc_regime(tickers)
    bt["bull"] = [bull(t) for t in bt["t"]]
    for lab, sub in bt.groupby("bull"):
        p(f"  {'bull' if lab else 'bear'}: {len(sub):4d} trades, net "
          f"{sub['net'].mean()*100:+.3f}%, win {(sub['net']>0).mean()*100:.0f}%")

    p("")
    p("G. CRASH-DAY CLUSTERING (calendar-day UTC, across tickers)")
    bt["day"] = pd.to_datetime(bt["t"], unit="ms").dt.date
    g = bt.groupby("day").agg(n=("net", "size"), pnl=("pnl", "sum"),
                              net=("net", "mean"))
    p(f"  {len(bt)} trades on {len(g)} distinct days | max same-day entries "
      f"{g['n'].max()} | days with >=5 entries: {(g['n']>=5).sum()}")
    p(f"  per-day mean net {g['net'].mean()*100:+.3f}% | days positive "
      f"{(g['net']>0).mean()*100:.0f}%")
    tot = g["pnl"].abs().sum()
    top = g["pnl"].abs().sort_values(ascending=False).head(5)
    p(f"  top-5 days = {top.sum()/tot*100:.0f}% of gross |pnl| "
      f"({', '.join(str(d) for d in top.index)})")
    sub = bt[~bt["day"].isin(top.index)]
    p(f"  excluding those 5 days entirely: net/trade "
      f"{sub['net'].mean()*100:+.3f}% ({len(sub)} trades)")

    p("")
    p("H. CONTEXT — mirror rule (prior candidate) on same machinery: "
      "+2.15%/88tr, dd -2.3%, positive all 4 years incl 2026.")
    p("   Capitulation long is the data-mined, higher-frequency, "
      "higher-expectancy book; its cost is crash-day concurrency, deeper "
      "dd, and a weak 2026.")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/capit_long_robustness_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
