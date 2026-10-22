#!/usr/bin/env python3
"""Long-strategy search on the full-span dataset (2023-01 -> 2026-10).

Prior long attempts: drift-long failed twice (beta), momo-long only works
2023-24, pump-long mirror weak. The one untested lead: the PANIC/CAPITULATION
long (+16.2%/trade, 100% win, but n=6 — parked with "loosen in round 2").
The traders' own fade ingredient (buy into adverse moves, +0.64% median
bounce) also points long-after-dump.

Three sections, all defined up front — report everything, no cherry-pick:
  1. DUMP EVENT STUDY — what actually happens after a >=12%/4h dump,
     split by first-green-close / volume spike / lower-wick. Grounds the
     rule in data the same way the pump anatomy grounded the short.
  2. BETA BASELINE — per-year mean forward return of EVERY alive bar at the
     tested holds (the census random-long control). Any long variant must
     clear its year's baseline, not zero — this is what killed rule D.
  3. VARIANT GRID — dump-long mirror of the frozen short (dump >= X%/4h,
     first green close, vol spike, stop = 4h low) and a loosening ladder
     of the panic long, through the identical portfolio/kill-switch
     machinery used by every prior backtest.

Usage: python3 long_search.py
Writes: reports/long_search_<stamp>.txt, backtest/trades_longsearch.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from backtest import M15
from rules_backtest import TAKER, SLIP
from regime_switch_backtest import load_full, WINDOWS
from indicator_tests import portfolio

COST = 2 * TAKER + SLIP
YEARS = (2023, 2024, 2025, 2026)

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


# ------------------------------------------------------------ precompute
def precompute(d):
    t, o, h, l, c, v = d["t"], d["o"], d["h"], d["l"], d["c"], d["v"]
    n = len(t)
    gap = np.zeros(n, bool)
    gap[16:] = (t[16:] - t[:-16]) == 16 * M15
    vpos = pd.Series(v > 0).rolling(9).min().to_numpy() == 1
    d["alive_v"] = gap & vpos & (h != l) & (np.arange(n) >= 20)
    r4 = np.full(n, np.nan)
    r4[16:] = c[16:] / c[:-16] - 1
    d["ret4_v"] = r4
    green = np.zeros(n, bool)
    green[1:] = c[1:] > c[:-1]
    d["green_v"] = green
    mu = pd.Series(v).rolling(8).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["volr_v"] = np.where(mu > 0, v / mu, np.nan)
    # synthetic rolling 4h candle (O = open 15 bars back, H/L window extremes)
    O = np.concatenate([np.full(15, o[0]), o[:-15]])
    Hh = pd.Series(h).rolling(16).max().to_numpy()
    Ll = pd.Series(l).rolling(16).min().to_numpy()
    rng = Hh - Ll
    with np.errstate(divide="ignore", invalid="ignore"):
        d["lowick_v"] = np.where(rng > 0, (np.minimum(O, c) - Ll) / rng, np.nan)
        d["upwick_v"] = np.where(rng > 0, (Hh - np.maximum(O, c)) / rng, np.nan)
        d["cloc_v"] = np.where(rng > 0, (c - Ll) / rng, np.nan)
    d["L4_v"] = Ll


def fwd_ret(d, idx, k):
    """Clean k-bar forward close return for each index (NaN if gap/end)."""
    t, c = d["t"], d["c"]
    n = len(t)
    out = np.full(len(idx), np.nan)
    ok = idx + k < n
    j = np.where(ok, idx + k, 0)
    clean = ok & (t[j] - t[idx] == k * M15)
    out[clean] = c[j[clean]] / c[idx[clean]] - 1
    return out


# --------------------------------------------------------- 1. event study
def event_study(tickers):
    p("=" * 100)
    p("1. DUMP EVENT STUDY — alive bars with 4h return <= -12%, per-ticker 24h cooldown")
    rows = []
    for tk, d in tickers.items():
        t = d["t"]
        cand = np.nonzero(d["alive_v"] & (d["ret4_v"] <= -0.12))[0]
        last = -10**18
        for i in cand:
            if t[i] - last < 96 * M15:
                continue
            last = t[i]
            rows.append((tk, i))
    by_tk = {}
    for tk, i in rows:
        by_tk.setdefault(tk, []).append(i)
    recs = []
    for tk, ii in by_tk.items():
        d = tickers[tk]
        idx = np.array(ii)
        f = {k: fwd_ret(d, idx, k) for k in (2, 4, 8, 16, 32, 96)}
        for z, i in enumerate(idx):
            recs.append(dict(
                ticker=tk, t=d["t"][i],
                year=pd.to_datetime(d["t"][i], unit="ms").year,
                green=bool(d["green_v"][i]), volr=d["volr_v"][i],
                lowick=d["lowick_v"][i], cloc=d["cloc_v"][i],
                ret4=d["ret4_v"][i],
                **{f"f{k}": f[k][z] for k in f}))
    ev = pd.DataFrame(recs)
    p(f"events: {len(ev):,} across {ev['ticker'].nunique()} tickers")
    hz = [("30m", "f2"), ("1h", "f4"), ("2h", "f8"), ("4h", "f16"),
          ("8h", "f32"), ("24h", "f96")]

    def show(label, g):
        if len(g) < 5:
            p(f"  {label:34s} n={len(g):5,}  (too few)")
            return
        parts = " ".join(f"{h}:{g[c].mean()*100:+.2f}%" for h, c in hz)
        p(f"  {label:34s} n={len(g):5,}  {parts}")

    p("")
    p("mean forward return from event close (gross, no costs):")
    show("ALL dumps", ev)
    show("first green close", ev[ev["green"]])
    show("still red", ev[~ev["green"]])
    show("green + vol>=2x", ev[ev["green"] & (ev["volr"] >= 2)])
    show("green + lowick>=0.3", ev[ev["green"] & (ev["lowick"] >= 0.3)])
    show("green + vol>=2x + lowick>=0.3",
         ev[ev["green"] & (ev["volr"] >= 2) & (ev["lowick"] >= 0.3)])
    show("deeper dump <= -20%", ev[ev["ret4"] <= -0.20])
    show("deeper + green", ev[(ev["ret4"] <= -0.20) & ev["green"]])
    p("")
    p("by year (ALL dumps vs green+vol>=2x), 4h and 24h horizons:")
    for y in YEARS:
        a = ev[ev["year"] == y]
        b = a[a["green"] & (a["volr"] >= 2)]
        p(f"  {y}: all n={len(a):4,} 4h {a['f16'].mean()*100:+.2f}% "
          f"24h {a['f96'].mean()*100:+.2f}%   |   green+vol n={len(b):3,} "
          f"4h {(b['f16'].mean()*100 if len(b) else float('nan')):+.2f}% "
          f"24h {(b['f96'].mean()*100 if len(b) else float('nan')):+.2f}%")
    p("")
    p("dose-response (dump depth ladder, green+vol>=2x, 4h horizon):")
    for lo, hi_ in ((-0.16, -0.12), (-0.20, -0.16), (-0.30, -0.20), (-1.0, -0.30)):
        g = ev[(ev["ret4"] > lo) & (ev["ret4"] <= hi_) &
               ev["green"] & (ev["volr"] >= 2)]
        show(f"dump in ({lo:+.0%}, {hi_:+.0%}]", g)
    return ev


# --------------------------------------------------------- 2. beta anchor
def beta_baseline(tickers):
    p("")
    p("=" * 100)
    p("2. BETA BASELINE — mean net fwd return of EVERY alive bar (long, taker "
      f"costs {COST*100:.2f}%) — the bar any long variant must clear")
    recs = []
    for tk, d in tickers.items():
        idx = np.nonzero(d["alive_v"])[0][::4]          # every hour, census-ish
        if not len(idx):
            continue
        yr = pd.to_datetime(d["t"][idx], unit="ms").year
        for k in (16, 32, 96):
            fr = fwd_ret(d, idx, k)
            m = ~np.isnan(fr)
            recs.append(pd.DataFrame(dict(year=yr[m], k=k, net=fr[m] - COST)))
    b = pd.concat(recs)
    hdr = "  year " + " ".join(f"{h:>10s}" for h in ("4h", "8h", "24h"))
    p(hdr)
    base = {}
    for y in YEARS:
        row = f"  {y} "
        for k in (16, 32, 96):
            g = b[(b["year"] == y) & (b["k"] == k)]
            base[(y, k)] = g["net"].mean()
            row += f"{g['net'].mean()*100:+9.3f}% "
        p(row)
    return base


# --------------------------------------------------------- 3. variant grid
def sigs_long(tickers, t0, t1, dump=0.12, volx=2.0, green=True,
              lowick=None, cloc=None, hold=16, stop_pad=0.999):
    rows = []
    for tk, d in tickers.items():
        t = d["t"]
        lo = max(np.searchsorted(t, t0 - M15), 20)
        hi = np.searchsorted(t, t1 - M15)
        cond = d["alive_v"] & (d["ret4_v"] <= -dump) & (d["volr_v"] >= volx)
        if green:
            cond = cond & d["green_v"]
        if lowick is not None:
            cond = cond & (d["lowick_v"] >= lowick)
        if cloc is not None:
            cond = cond & (d["cloc_v"] >= cloc)
        cond[:lo] = False
        cond[hi:] = False
        for i in np.nonzero(cond)[0]:
            rows.append((t[i] + M15, tk, i, 1, d["L4_v"][i] * stop_pad, hold))
    return rows


def run_variant(label, tickers, store, **kw):
    allt, rets, dds = [], [], []
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = sigs_long(tickers, t0, t1, **kw)
        trades, eqh = portfolio(rows, tickers)
        met = metrics(eqh, t0, t1)
        rets.append(met["ret"])
        dds.append(met["maxdd"])
        allt += trades
    g = pd.DataFrame(allt) if allt else pd.DataFrame(
        columns=["net", "t", "kind", "ticker", "side"])
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
    p(f"{label:36s} {len(g):5,} {nt:+8.3f}% {md:+8.3f}% {wr:4.0f}% {slr:4.0f}% "
      f"{comp*100:+8.2f}% {min(dds)*100:6.1f}%  " + " | ".join(posy))
    if len(g):
        g["variant"] = label
        store.append(g)
    return g


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"LONG-STRATEGY SEARCH — {stamp} | full span 2023-01 -> 2026-10")
    p(f"costs {COST*100:.2f}%/round-trip taker+slip | portfolio machinery "
      "identical to fleet backtests")
    tickers = load_full()
    p(f"universe: {len(tickers)} tickers")
    for d in tickers.values():
        precompute(d)

    event_study(tickers)
    beta_baseline(tickers)

    p("")
    p("=" * 100)
    p("3. VARIANT GRID — full portfolio sim (stops, sizing, kill-switch, "
      "MAX_CONC)")
    hdr = (f"{'variant':36s} {'trades':>5s} {'net/tr':>8s} {'median':>8s} "
           f"{'win%':>4s} {'sl%':>4s} {'comp':>8s} {'dd':>6s}  by year")
    store = []

    p("")
    p("A. DUMP-LONG MIRROR of frozen short (first green close, stop=4h low)")
    p(hdr)
    run_variant("M base d12 v2 h16", tickers, store)
    run_variant("M d08", tickers, store, dump=0.08)
    run_variant("M d16", tickers, store, dump=0.16)
    run_variant("M d20", tickers, store, dump=0.20)
    run_variant("M v1.5", tickers, store, volx=1.5)
    run_variant("M v3", tickers, store, volx=3.0)
    run_variant("M h8", tickers, store, hold=8)
    run_variant("M h32", tickers, store, hold=32)
    run_variant("M h96", tickers, store, hold=96)
    run_variant("M no-green", tickers, store, green=False)
    run_variant("M +lowick.30", tickers, store, lowick=0.30)
    run_variant("M +cloc.50", tickers, store, cloc=0.50)
    run_variant("M +lowick.30 +cloc.50", tickers, store,
                lowick=0.30, cloc=0.50)

    p("")
    p("B. PANIC LONG loosening ladder (anatomy entry, green not required)")
    p(hdr)
    run_variant("P orig d15 v3 lw.40 cl.50 h32", tickers, store,
                dump=0.15, volx=3.0, green=False, lowick=0.40, cloc=0.50,
                hold=32)
    run_variant("P d12 v2.5 lw.30 cl.50 h32", tickers, store,
                dump=0.12, volx=2.5, green=False, lowick=0.30, cloc=0.50,
                hold=32)
    run_variant("P d12 v2 lw.25 cl.40 h32", tickers, store,
                dump=0.12, volx=2.0, green=False, lowick=0.25, cloc=0.40,
                hold=32)
    run_variant("P d10 v2 lw.25 cl.40 h32", tickers, store,
                dump=0.10, volx=2.0, green=False, lowick=0.25, cloc=0.40,
                hold=32)
    run_variant("P d12 v2 lw.25 cl.40 h8", tickers, store,
                dump=0.12, volx=2.0, green=False, lowick=0.25, cloc=0.40,
                hold=8)
    run_variant("P d12 v2 lw.25 cl.40 h16", tickers, store,
                dump=0.12, volx=2.0, green=False, lowick=0.25, cloc=0.40,
                hold=16)
    run_variant("P d12 v2 lw.25 cl.40 h96", tickers, store,
                dump=0.12, volx=2.0, green=False, lowick=0.25, cloc=0.40,
                hold=96)

    p("")
    p("READ AGAINST SECTION 2: a year's net/trade must beat that year's beta")
    p("baseline at the matching hold, or the variant is drift in costume.")

    if store:
        t = pd.concat(store)
        t.to_csv("backtest/trades_longsearch.csv.gz", index=False,
                 compression="gzip")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/long_search_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
