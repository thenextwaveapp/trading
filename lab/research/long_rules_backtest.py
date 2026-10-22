#!/usr/bin/env python3
"""Variant backtest of the DATA-MINED long rule family (from long_miner.py).

What the Invo long data actually says (reports/long_miner_*):
  - #1 edge = intra-hour dip catch (f_pre_lo1h <= -2%: +7.4%/30m) but it is
    FRONT-LOADED -> paper-fill mirage for a candle-close bot. Verified here
    honestly in section 0 before anything else.
  - #2 edge = DUMP entries: f_ret_4h <= -5% -> +2.05%/4h GROWING to
    +2.62%/24h (not front-loaded => implementable). Skilled cohort gets
    +6.6%/4h on the same condition. Winners share elevated natr, low 24h
    range position; they do NOT wait for a green close; median MAE -1.8%
    (tight stops would clip half the winners); edge accrues toward 24h
    (wants long holds).

Rule family tested (params read off the mined distributions, declared here):
  trigger : 4h return <= -D on FRESH crossing (newly true this bar), or
            24h return <= -D24 fresh crossing
  filters : none / natr above own 30d median / range_pos_24h <= 0.3 /
            green close / vol15 >= 2 (the last two bridge to the old mirror)
  hold    : 16 / 32 / 96 bars (4h / 8h / 24h)
  stop    : none (time exit) / 2*natr / 4h-low   (sizing basis fixed at
            2*natr for all variants)
  entry   : close of signal bar (bot-realistic), taker costs both ways

Usage: python3 long_rules_backtest.py
Writes: reports/long_rules_<stamp>.txt, backtest/trades_longrules.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from regime_switch_backtest import load_full, WINDOWS
from long_search import COST, YEARS, fwd_ret
from long_robustness import portfolio

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- features
def precompute2(d):
    t, o, h, l, c, v = d["t"], d["o"], d["h"], d["l"], d["c"], d["v"]
    n = len(t)
    gap16 = np.zeros(n, bool)
    gap16[16:] = (t[16:] - t[:-16]) == 16 * M15
    gap96 = np.zeros(n, bool)
    gap96[96:] = (t[96:] - t[:-96]) == 96 * M15
    vpos = pd.Series(v > 0).rolling(9).min().to_numpy() == 1
    d["alive_v"] = gap16 & vpos & (h != l) & (np.arange(n) >= 100)
    d["alive96_v"] = d["alive_v"] & gap96
    r4 = np.full(n, np.nan)
    r4[16:] = c[16:] / c[:-16] - 1
    d["ret4_v"] = r4
    r24 = np.full(n, np.nan)
    r24[96:] = c[96:] / c[:-96] - 1
    d["ret24_v"] = r24
    green = np.zeros(n, bool)
    green[1:] = c[1:] > c[:-1]
    d["green_v"] = green
    mu = pd.Series(v).rolling(8).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["volr_v"] = np.where(mu > 0, v / mu, np.nan)
    cprev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - cprev), np.abs(l - cprev)))
    natr = pd.Series(tr).rolling(96).mean().to_numpy() / c
    d["natr_v"] = natr
    med30 = pd.Series(natr).rolling(2880, min_periods=960).median().to_numpy()
    d["natr_hi_v"] = natr > med30
    lo96 = pd.Series(l).rolling(96).min().to_numpy()
    hi96 = pd.Series(h).rolling(96).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["rpos_v"] = np.where(hi96 > lo96, (c - lo96) / (hi96 - lo96), np.nan)
    d["lo4h_v"] = pd.Series(l).rolling(16).min().to_numpy()
    # intra-bar dip vs previous close (for the mirage check)
    d["dip_v"] = np.full(n, np.nan)
    d["dip_v"][1:] = l[1:] / c[:-1] - 1


# ------------------------------------------------- 0. dip-catch mirage check
def mirage_check(tickers):
    p("=" * 100)
    p("0. DIP-CATCH MIRAGE CHECK — bars whose intra-bar low is <= -2% below "
      "prev close (the traders' f_pre_lo1h dip)")
    p("   trader fill = intra-dip; a bot fills at BAR CLOSE. Return from "
      "close -> +4h/+24h is what a bot would get (gross):")
    recs = []
    for tk, d in tickers.items():
        idx = np.nonzero(d["alive_v"] & (d["dip_v"] <= -0.02))[0]
        # 24h per-ticker cooldown
        keep, last = [], -10**18
        for i in idx:
            if d["t"][i] - last >= 96 * M15:
                keep.append(i)
                last = d["t"][i]
        if not keep:
            continue
        idx = np.array(keep)
        lowret = d["dip_v"][idx]                       # dip depth vs prev close
        bounce = d["c"][idx] / (d["l"][idx])           # low -> close recovery
        f16 = fwd_ret(d, idx, 16)
        f96 = fwd_ret(d, idx, 96)
        yr = pd.to_datetime(d["t"][idx], unit="ms").year
        recs.append(pd.DataFrame(dict(year=yr, dip=lowret, bounce=bounce - 1,
                                      f4h=f16, f24h=f96)))
    e = pd.concat(recs)
    p(f"   events: {len(e):,} | mean dip depth {e['dip'].mean()*100:+.2f}% | "
      f"mean low->close bounce already gone by close: "
      f"{e['bounce'].mean()*100:+.2f}%")
    p(f"   from CLOSE: 4h {e['f4h'].mean()*100:+.3f}% | 24h "
      f"{e['f24h'].mean()*100:+.3f}%  (vs trader-fill +6-7%/4h)")
    for y in YEARS:
        g = e[e["year"] == y]
        p(f"     {y}: n={len(g):5,} 4h {g['f4h'].mean()*100:+.3f}% "
          f"24h {g['f24h'].mean()*100:+.3f}%")


# ---------------------------------------------------------------- signals
def gen_signals(d, t0, t1, trig="r4", depth=0.05, natr_hi=False,
                rpos=None, green=False, volx=None):
    t = d["t"]
    lo = max(np.searchsorted(t, t0 - M15), 100)
    hi = np.searchsorted(t, t1 - M15)
    base = d["ret4_v"] <= -depth if trig == "r4" else d["ret24_v"] <= -depth
    alive = d["alive_v"] if trig == "r4" else d["alive96_v"]
    cond = alive & base
    if natr_hi:
        cond = cond & d["natr_hi_v"]
    if rpos is not None:
        cond = cond & (d["rpos_v"] <= rpos)
    if green:
        cond = cond & d["green_v"]
    if volx is not None:
        cond = cond & (d["volr_v"] >= volx)
    fresh = cond.copy()
    fresh[1:] = cond[1:] & ~cond[:-1]        # newly true this bar
    fresh[:lo] = False
    fresh[hi:] = False
    return [(t[i] + M15, i) for i in np.nonzero(fresh)[0]]


def make_exit(hold=96, stop_mode="none", cost_mult=1.0):
    cost = COST * cost_mult

    def exit_fn(d, i):
        t, l, c = d["t"], d["l"], d["c"]
        entry = c[i]
        natr = d["natr_v"][i]
        sl_dist = max(2 * natr if natr == natr else 0.02, 0.005)  # sizing basis
        level = {"none": -np.inf,
                 "natr2": entry * (1 - 2 * (natr if natr == natr else 0.02)),
                 "lo4h": d["lo4h_v"][i] * 0.999}[stop_mode]
        for j in range(i + 1, min(i + hold + 1, len(t))):
            if l[j] < level:
                return (level / entry - 1) - cost, t[j] + M15, "sl", sl_dist
        j = min(i + hold, len(t) - 1)
        return (c[j] / entry - 1) - cost, t[j] + M15, "time", sl_dist

    return exit_fn


def run_variant(tickers, label, store, hold=96, stop_mode="none",
                cost_mult=1.0, **sig_kw):
    exit_fn = make_exit(hold, stop_mode, cost_mult)
    all_trades, rets, dds = [], [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i) for tsg, i in gen_signals(d, t0, t1, **sig_kw)]
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
    slr = (g["kind"] == "sl").mean() * 100 if len(g) else 0
    posy = []
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        for y in YEARS:
            gy = g[g["year"] == y]
            posy.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy)}"
                        if len(gy) else f"{y}: --")
    p(f"{label:38s} {len(g):5,} {nt:+8.3f}% {md:+8.3f}% {wr:4.0f}% {slr:4.0f}% "
      f"{comp*100:+8.2f}% {min(dds)*100:6.1f}%  " + " | ".join(posy))
    if len(g):
        g["variant"] = label
        store.append(g)
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"DATA-MINED LONG RULES — VARIANT BACKTEST — {stamp} | "
      "full span 2023-01 -> 2026-10")
    p(f"entry at signal-bar close, taker costs {COST*100:.2f}% round trip, "
      "fleet portfolio machinery")
    tickers = load_full()
    for d in tickers.values():
        precompute2(d)
    p(f"universe: {len(tickers)} tickers")
    p("")

    mirage_check(tickers)

    hdr = (f"{'variant':38s} {'trades':>5s} {'net/tr':>8s} {'median':>8s} "
           f"{'win%':>4s} {'sl%':>4s} {'comp':>8s} {'dd':>6s}  by year")
    store = []

    p("")
    p("=" * 100)
    p("A. DUMP-4H FAMILY (traders' condition: f_ret_4h <= -5%), fresh "
      "crossing, hold 24h, no stop")
    p(hdr)
    run_variant(tickers, "D4 base: r4<=-5% h96", store,
                trig="r4", depth=0.05)
    run_variant(tickers, "D4 depth -4%", store, trig="r4", depth=0.04)
    run_variant(tickers, "D4 depth -6%", store, trig="r4", depth=0.06)
    run_variant(tickers, "D4 depth -8%", store, trig="r4", depth=0.08)
    run_variant(tickers, "D4 depth -12%", store, trig="r4", depth=0.12)
    run_variant(tickers, "D4 hold 16 (4h)", store, trig="r4", depth=0.05,
                hold=16)
    run_variant(tickers, "D4 hold 32 (8h)", store, trig="r4", depth=0.05,
                hold=32)
    run_variant(tickers, "D4 +natr-high", store, trig="r4", depth=0.05,
                natr_hi=True)
    run_variant(tickers, "D4 +rpos<=0.3", store, trig="r4", depth=0.05,
                rpos=0.3)
    run_variant(tickers, "D4 +natr +rpos", store, trig="r4", depth=0.05,
                natr_hi=True, rpos=0.3)
    run_variant(tickers, "D4 +green close", store, trig="r4", depth=0.05,
                green=True)
    run_variant(tickers, "D4 +vol>=2x", store, trig="r4", depth=0.05,
                volx=2.0)
    run_variant(tickers, "D4 stop 2*natr", store, trig="r4", depth=0.05,
                stop_mode="natr2")
    run_variant(tickers, "D4 stop 4h-low", store, trig="r4", depth=0.05,
                stop_mode="lo4h")

    p("")
    p("B. DUMP-24H FAMILY (f_ret_24h <= -10%), fresh crossing, hold 24h, "
      "no stop")
    p(hdr)
    run_variant(tickers, "D24 base: r24<=-10% h96", store,
                trig="r24", depth=0.10)
    run_variant(tickers, "D24 depth -8%", store, trig="r24", depth=0.08)
    run_variant(tickers, "D24 depth -15%", store, trig="r24", depth=0.15)
    run_variant(tickers, "D24 depth -20%", store, trig="r24", depth=0.20)
    run_variant(tickers, "D24 hold 16", store, trig="r24", depth=0.10,
                hold=16)
    run_variant(tickers, "D24 hold 32", store, trig="r24", depth=0.10,
                hold=32)
    run_variant(tickers, "D24 +natr-high", store, trig="r24", depth=0.10,
                natr_hi=True)
    run_variant(tickers, "D24 +natr +rpos<=0.3", store, trig="r24",
                depth=0.10, natr_hi=True, rpos=0.3)

    p("")
    p("C. TRADER-SHAPED COMBO (dump + vol expansion, the skilled-cohort "
      "profile) + cost stress on the best-prior-family point")
    p(hdr)
    run_variant(tickers, "D4 -5% +natr h96 costs x2", store, trig="r4",
                depth=0.05, natr_hi=True, cost_mult=2.0)
    run_variant(tickers, "D4 -5% +natr h96 costs x4", store, trig="r4",
                depth=0.05, natr_hi=True, cost_mult=4.0)

    p("")
    p("NOTE: beta baseline (long_search sec 2): 24h-hold census baseline "
      "2023 +0.18% / 2024 +0.14% / 2025 -0.29% / 2026 +0.00% — judge the "
      "h96 variants against THAT, not zero.")

    if store:
        t = pd.concat(store)
        t.to_csv("backtest/trades_longrules.csv.gz", index=False,
                 compression="gzip")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/long_rules_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
