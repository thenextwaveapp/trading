#!/usr/bin/env python3
"""Capitulation-long VARIANTS ROUND 2 — new axes not touched by round 1.

Base (fixed): 24h ret <= -20% fresh crossing + BTC bear (4h EMA20<EMA50)
-> long, time exit 96c (24h), no stop. All variants below are bear-gated
at -20% unless stated.

New axes:
  1. ENTRY EXECUTION — limit orders below the signal close (-2/-4/-6%,
     filled only if price actually trades there within 4h; unfilled =
     skipped): can a bot recover part of the traders' intra-dip fills?
     Plus: wait-for-first-green-close entry (confirmation delay).
  2. EXIT STYLE — trailing stop from post-entry peak (10/20%), breakeven
     lock after +10%, split exit (half at 24h, half at 48h).
  3. RE-ENTRY — allow repeat signal every 24h while condition persists
     (averaging into extended crashes) vs base fresh-crossing-only.
  4. UNIVERSE — majors vs small caps; idiosyncratic dump (coin -20% while
     BTC flat-ish) vs market-wide crash day (BTC itself down >= 5%/24h).
  5. BREADTH GATE — how many tickers signaled in the last 24h: isolated
     (<3) vs clustered (>=3) crash days.

Usage: python3 capit_variants2_backtest.py
Writes: reports/capit_variants2_<stamp>.txt, backtest/trades_capitv2.csv.gz
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

DAY = 86_400_000
MAJORS = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK",
          "AVAX", "LTC"}

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- exits
def make_exit(hold=96, mode="time", limit=None, trail=None, be_arm=None,
              confirm_green=False):
    """mode: time | split (half 96 / half 192).
    limit: entry = signal close * (1 - limit), filled only if traded within
    16 bars; hold counted from fill bar. trail: stop at post-entry peak*(1-t).
    be_arm: after high > entry*(1+arm), stop moves to entry.
    confirm_green: enter at first green close within 16 bars of signal."""
    def exit_fn(d, i):
        t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
        n = len(t)
        natr = d["natr_v"][i]
        sl_dist = max(2 * natr if natr == natr else 0.02, 0.005)
        # ---- entry resolution
        start, entry = i, c[i]
        if limit is not None:
            lv = c[i] * (1 - limit)
            start = None
            for j in range(i + 1, min(i + 17, n)):
                if l[j] <= lv:
                    start, entry = j, lv
                    break
            if start is None:
                return None                       # never filled -> no trade
        elif confirm_green:
            start = None
            for j in range(i + 1, min(i + 17, n)):
                if c[j] > c[j - 1]:
                    start, entry = j, c[j]
                    break
            if start is None:
                return None
        # ---- exit resolution
        end = min(start + hold, n - 1)
        if mode == "split":
            e1 = min(start + 96, n - 1)
            e2 = min(start + 192, n - 1)
            net = 0.5 * (c[e1] / entry - 1) + 0.5 * (c[e2] / entry - 1) - COST
            return net, t[e2] + M15, "time", sl_dist
        peak, stop_lv = entry, -np.inf
        for j in range(start + 1, end + 1):
            if trail is not None:
                stop_lv = max(stop_lv, peak * (1 - trail))
            if be_arm is not None and peak > entry * (1 + be_arm):
                stop_lv = max(stop_lv, entry)
            if l[j] < stop_lv:
                return (stop_lv / entry - 1) - COST, t[j] + M15, "sl", sl_dist
            peak = max(peak, h[j])
        return (c[end] / entry - 1) - COST, t[end] + M15, "time", sl_dist
    return exit_fn


# ------------------------------------------------------------- signal gens
def sigs_reentry(d, t0, t1, depth=0.20, every=96):
    """Condition true -> signal every `every` bars while it stays true."""
    t = d["t"]
    lo = max(np.searchsorted(t, t0 - M15), 100)
    hi = np.searchsorted(t, t1 - M15)
    cond = d["alive96_v"] & (d["ret24_v"] <= -depth)
    cond[:lo] = False
    cond[hi:] = False
    out, last = [], -10**18
    for i in np.nonzero(cond)[0]:
        if t[i] - last >= every * M15:
            out.append((t[i] + M15, i))
            last = t[i]
    return out


def run(tickers, label, store, gate=None, sig_fn=None, exit_kw=None,
        tick_filter=None, sig_filter=None):
    exit_fn = make_exit(**(exit_kw or {}))
    allt, rets, dds = [], [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            if tick_filter and not tick_filter(tk):
                continue
            if sig_fn:
                sigs = sig_fn(d, t0, t1)
            else:
                sigs = gen_signals(d, t0, t1, trig="r24", depth=0.20)
            rows += [(tsg, tk, i) for tsg, i in sigs]
        if gate:
            rows = [r for r in rows if gate(r[0])]
        if sig_filter:
            rows = [r for r in rows if sig_filter(r)]
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
    posy, yrs_pos = [], 0
    if len(g):
        g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
        for y in YEARS:
            gy = g[g["year"] == y]
            posy.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy)}"
                        if len(gy) else f"{y}: --")
            yrs_pos += int(len(gy) > 0 and gy["net"].mean() > 0)
    p(f"{label:34s} {len(g):5,} {nt:+8.3f}% {md:+7.2f}% {wr:4.0f}% "
      f"{comp*100:+9.2f}% {min(dds)*100:6.1f}% {yrs_pos}/4  "
      + " | ".join(posy))
    if len(g):
        g["variant"] = label
        store.append(g)
    return dict(variant=label, trades=len(g), net=nt, win=wr,
                comp=comp * 100, dd=min(dds) * 100, yrs_pos=yrs_pos)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute2(d)
    bull = btc_regime(tickers)
    bear = lambda T: not bull(T)
    p(f"CAPIT-LONG VARIANTS ROUND 2 — {stamp} | {len(tickers)} tickers | "
      "full span 2023-01 -> 2026-10")
    p("base = -20%/24h fresh + BTC bear -> long at close, no stop, hold 96c")
    p("")

    # BTC 24h return lookup (for idio/market-wide splits)
    db = tickers["BTC"]
    bt_t, bt_r = db["t"], db["ret24_v"]
    def btc_r24(T):
        j = np.searchsorted(bt_t, T - M15, "right") - 1
        return bt_r[j] if j >= 0 and bt_r[j] == bt_r[j] else 0.0

    # global signal times (bear-gated base) for breadth gate
    all_sig = []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        for tk, d in tickers.items():
            all_sig += [tsg for tsg, i in
                        gen_signals(d, t0, t1, trig="r24", depth=0.20)]
    all_sig = np.array(sorted(all_sig))
    def breadth(T):
        lo = np.searchsorted(all_sig, T - DAY)
        hi = np.searchsorted(all_sig, T)
        return hi - lo                      # signals in trailing 24h (any tk)

    hdr = (f"{'variant':34s} {'trades':>5s} {'net/tr':>8s} {'median':>7s} "
           f"{'win%':>4s} {'comp':>9s} {'dd':>6s} {'y+':>3s}  by year")
    store, summ = [], []

    p("0. REFERENCE")
    p(hdr)
    summ.append(run(tickers, "BASE bear -20% h96", store, gate=bear))

    p("")
    p("1. ENTRY EXECUTION (bear-gated)")
    p(hdr)
    for lim in (0.02, 0.04, 0.06):
        summ.append(run(tickers, f"limit entry -{lim:.0%} (16c window)",
                        store, gate=bear, exit_kw=dict(limit=lim)))
    summ.append(run(tickers, "wait first green close", store, gate=bear,
                    exit_kw=dict(confirm_green=True)))

    p("")
    p("2. EXIT STYLE (bear-gated)")
    p(hdr)
    summ.append(run(tickers, "trail 10% from peak", store, gate=bear,
                    exit_kw=dict(trail=0.10)))
    summ.append(run(tickers, "trail 20% from peak", store, gate=bear,
                    exit_kw=dict(trail=0.20)))
    summ.append(run(tickers, "breakeven lock after +10%", store, gate=bear,
                    exit_kw=dict(be_arm=0.10)))
    summ.append(run(tickers, "split: half 24h, half 48h", store, gate=bear,
                    exit_kw=dict(mode="split")))
    summ.append(run(tickers, "trail 20% + 192c window", store, gate=bear,
                    exit_kw=dict(trail=0.20, hold=192)))

    p("")
    p("3. RE-ENTRY POLICY (bear-gated)")
    p(hdr)
    summ.append(run(tickers, "re-enter every 24h in dump", store, gate=bear,
                    sig_fn=lambda d, a, b: sigs_reentry(d, a, b, every=96)))
    summ.append(run(tickers, "re-enter every 48h in dump", store, gate=bear,
                    sig_fn=lambda d, a, b: sigs_reentry(d, a, b, every=192)))

    p("")
    p("4. UNIVERSE / CRASH TYPE (bear-gated)")
    p(hdr)
    summ.append(run(tickers, "majors only", store, gate=bear,
                    tick_filter=lambda tk: tk in MAJORS))
    summ.append(run(tickers, "small caps only", store, gate=bear,
                    tick_filter=lambda tk: tk not in MAJORS))
    summ.append(run(tickers, "idio dump (BTC 24h > -5%)", store, gate=bear,
                    sig_filter=lambda r: btc_r24(r[0]) > -0.05))
    summ.append(run(tickers, "market-wide (BTC 24h <= -5%)", store,
                    gate=bear, sig_filter=lambda r: btc_r24(r[0]) <= -0.05))

    p("")
    p("5. BREADTH GATE (bear-gated; signals from any ticker in last 24h)")
    p(hdr)
    summ.append(run(tickers, "isolated: breadth < 3", store, gate=bear,
                    sig_filter=lambda r: breadth(r[0]) < 3))
    summ.append(run(tickers, "clustered: breadth >= 3", store, gate=bear,
                    sig_filter=lambda r: breadth(r[0]) >= 3))
    summ.append(run(tickers, "panic: breadth >= 6", store, gate=bear,
                    sig_filter=lambda r: breadth(r[0]) >= 6))

    p("")
    p("=" * 100)
    p("RANKED (by net/trade, min 40 trades; **** = positive all 4 years)")
    s = pd.DataFrame(summ)
    s = s[s["trades"] >= 40].sort_values("net", ascending=False)
    for _, r in s.iterrows():
        flag = " ****" if r["yrs_pos"] == 4 else ""
        p(f"  {r['variant']:34s} {r['net']:+8.3f}%/tr x{r['trades']:4,} | "
          f"win {r['win']:3.0f}% | comp {r['comp']:+9.2f}% | dd "
          f"{r['dd']:5.1f}%{flag}")

    if store:
        t = pd.concat(store)
        t.to_csv("backtest/trades_capitv2.csv.gz", index=False,
                 compression="gzip")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/capit_variants2_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
