#!/usr/bin/env python3
"""CAPIT_2H EVENT STUDY — what actually happens after a 2h cascade.

Events: 2h return <= -X% (X in 6/8/10/12), fresh crossing, 24h per-ticker
cooldown, gapless tape, Invo 60, both eras pooled (2023-01 .. 2026-10).
No costs — raw forward returns; this decides IF a strategy gets built.

Questions, in order:
  1. depth grid — mean forward return at +2h/+6h/+24h/+48h per depth
  2. entry style — at event close vs at FIRST GREEN close (<=3h after)
     vs cascades with no green inside 3h (the keep-bleeding subset)
  3. splits on the headline depth — BTC bear/bull at event, and overlap
     with the existing books (capit -20%/24h within +-24h, or 1h leg
     <= -3% = a loser3-style candidate) vs genuinely new events

Usage: python3 research/capit2h_event_study.py
Writes: reports/capit2h_events_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import M15
from rules_backtest import load

DEPTHS = (0.06, 0.08, 0.10, 0.12)
HORIZONS = [("2h", 8), ("6h", 24), ("24h", 96), ("48h", 192)]
GREEN_WIN = 12            # bars to wait for the first green close (3h)
DAY = 86_400_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def fwd(d, i, bars):
    t, c = d["t"], d["c"]
    j = i + bars
    if j >= len(t) or t[j] - t[i] != bars * M15:
        return np.nan
    return c[j] / c[i] - 1


def capit_times(d):
    """Fresh -20%/24h crossing times (the existing capit trigger)."""
    t, c = d["t"], d["c"]
    out = []
    for i in range(97, len(t)):
        if t[i] - t[i - 96] != 96 * M15:
            continue
        r = c[i] / c[i - 96] - 1
        rp = c[i - 1] / c[i - 97] - 1 if t[i - 1] - t[i - 97] == 96 * M15 \
            else 0.0
        if r <= -0.20 and rp > -0.20:
            out.append(t[i])
    return np.array(out, np.int64)


def collect(tickers, regime_at, depth):
    rows = []
    for tk, d in tickers.items():
        t, c, v, h, l = (d[k] for k in "tcvhl")
        cap_t = capit_times(d)
        last = -10**18
        n = len(t)
        for i in range(9, n - 1):
            if t[i] - last < DAY:
                continue
            if t[i] - t[i - 8] != 8 * M15:
                continue
            if (v[i - 8:i + 1] <= 0).any() or h[i] == l[i]:
                continue
            r2 = c[i] / c[i - 8] - 1
            if r2 > -depth:
                continue
            r2p = c[i - 1] / c[i - 9] - 1 if t[i - 1] - t[i - 9] == 8 * M15 \
                else 0.0
            if r2p <= -depth:                      # not a fresh crossing
                continue
            last = t[i]
            ev = dict(tk=tk, t=int(t[i]), r2=r2,
                      bear=(regime_at(t[i] + M15) is False),
                      loser_ov=(c[i] / c[i - 4] - 1 <= -0.03
                                if t[i] - t[i - 4] == 4 * M15 else False),
                      capit_ov=bool(len(cap_t) and
                                    (np.abs(cap_t - t[i]) <= DAY).any()))
            for lab, bars in HORIZONS:
                ev[f"f{lab}"] = fwd(d, i, bars)
            # first green close within GREEN_WIN bars
            jg = None
            for j in range(i + 1, min(i + 1 + GREEN_WIN, n)):
                if t[j] - t[j - 1] != M15:
                    break
                if c[j] > c[j - 1]:
                    jg = j
                    break
            ev["green"] = jg is not None
            if jg is not None:
                ev["g_delay"] = (jg - i) * 15
                for lab, bars in HORIZONS:
                    ev[f"g{lab}"] = fwd(d, jg, bars)
            rows.append(ev)
    return rows


def stat(df, col):
    s = df[col].dropna()
    if not len(s):
        return "      –"
    return f"{s.mean()*100:+6.2f}%"


def win(df, col):
    s = df[col].dropna()
    return f"{(s > 0).mean()*100:3.0f}%" if len(s) else "  –"


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"CAPIT_2H EVENT STUDY — {stamp} | Invo 60, 2023-01 .. 2026-10 "
      "pooled | no costs")
    p("")
    all_rows = {x: [] for x in DEPTHS}
    for c15, c1 in [("backtest/r60_oos_15m.csv.gz",
                     "backtest/r60_oos_1h.csv.gz"),
                    ("backtest/r60_candles_15m.csv.gz",
                     "backtest/r60_candles_1h.csv.gz")]:
        tickers, regime_at = load(c15, c1)
        for x in DEPTHS:
            all_rows[x] += collect(tickers, regime_at, x)
        del tickers

    p("1) DEPTH GRID — entry at event close")
    p(f"  {'depth':>6s} {'n':>5s}   {'+2h':>7s} {'+6h':>7s} {'+24h':>7s} "
      f"{'+48h':>7s}   {'win24':>5s}")
    for x in DEPTHS:
        df = pd.DataFrame(all_rows[x])
        p(f"  -{x*100:4.0f}% {len(df):5d}   {stat(df,'f2h')} {stat(df,'f6h')} "
          f"{stat(df,'f24h')} {stat(df,'f48h')}   {win(df,'f24h')}")
    p("")

    for x in (0.08, 0.10):
        df = pd.DataFrame(all_rows[x])
        g = df[df["green"]]
        ng = df[~df["green"]]
        p(f"2) ENTRY STYLE — depth -{x*100:.0f}% ({len(df)} events, "
          f"{len(g)} got a green close <=3h, median delay "
          f"{g['g_delay'].median() if len(g) else 0:.0f}m)")
        p(f"  {'entry':34s} {'n':>5s}   {'+6h':>7s} {'+24h':>7s} {'+48h':>7s}"
          f"   {'win24':>5s}")
        p(f"  {'at event close (knife)':34s} {len(df):5d}   "
          f"{stat(df,'f6h')} {stat(df,'f24h')} {stat(df,'f48h')}   "
          f"{win(df,'f24h')}")
        p(f"  {'at first green close':34s} {len(g):5d}   "
          f"{stat(g,'g6h')} {stat(g,'g24h')} {stat(g,'g48h')}   "
          f"{win(g,'g24h')}")
        p(f"  {'no green <=3h (kept bleeding)':34s} {len(ng):5d}   "
          f"{stat(ng,'f6h')} {stat(ng,'f24h')} {stat(ng,'f48h')}   "
          f"{win(ng,'f24h')}")
        p("")

    x = 0.10
    df = pd.DataFrame(all_rows[x])
    g = df[df["green"]]
    p(f"3) SPLITS — depth -{x*100:.0f}%, entry at first green close")
    p(f"  {'cell':34s} {'n':>5s}   {'+6h':>7s} {'+24h':>7s} {'+48h':>7s}"
      f"   {'win24':>5s}")
    cells = [
        ("BTC bear", g[g["bear"]]),
        ("BTC bull", g[~g["bear"]]),
        ("overlaps existing books", g[g["capit_ov"] | g["loser_ov"]]),
        ("NEW events (no overlap)", g[~(g["capit_ov"] | g["loser_ov"])]),
        ("new + bear (the folio slot)",
         g[~(g["capit_ov"] | g["loser_ov"]) & g["bear"]]),
        ("new + bull", g[~(g["capit_ov"] | g["loser_ov"]) & ~g["bear"]]),
    ]
    for lab, sub in cells:
        p(f"  {lab:34s} {len(sub):5d}   {stat(sub,'g6h')} "
          f"{stat(sub,'g24h')} {stat(sub,'g48h')}   {win(sub,'g24h')}")

    fname = ("reports/capit2h_events_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
