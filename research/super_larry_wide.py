#!/usr/bin/env python3
"""SUPER LARRY on the FULL universe — the original ladder backtest rerun on
the newly landed wide cache (every USDT perp ever listed on Binance futures,
delisted included — no survivorship bias). Same two tracks, same ladder,
same machinery as super_larry.py; universe = curated 60 (r60) + the wide
expansion. The era20 question asked at 2023-26 scale: does universe quality
still decide?

Per track it runs the ladder twice:
  CURATED 60   — must reproduce reports/super_larry_2026-10-11_0147.txt
                 (pipeline sanity check)
  FULL (60+N)  — signals, dial and trades from the whole universe

Usage: python3 research/super_larry_wide.py
Writes: reports/super_larry_wide_<stamp>.txt
"""
import gc
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import H
from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL

WDAYS, THR = 30, 0.0
USECOLS = ["ticker", "t", "o", "h", "l", "c", "v"]
CHUNK = 4_000_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def load_wide_era(t_lo, t_hi, skip):
    """Wide-cache tickers clipped to [t_lo, t_hi], built chunked to bound
    memory, shaped exactly like rules_backtest.load output."""
    frames1h, frames15 = {}, {}
    for path, acc in [("backtest/wide_1h.csv.gz", frames1h),
                      ("backtest/wide_15m.csv.gz", frames15)]:
        for ch in pd.read_csv(path, usecols=USECOLS, chunksize=CHUNK):
            ch = ch[(ch["t"] >= t_lo) & (ch["t"] <= t_hi)]
            for tk, g in ch.groupby("ticker"):
                acc.setdefault(tk, []).append(g)
    tickers = {}
    for tk, parts in frames15.items():
        if tk in skip or tk not in frames1h:
            continue
        g = pd.concat(parts).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        g1 = pd.concat(frames1h[tk]).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        if len(g) < 500 or len(g1) < 100:
            continue
        t = g["t"].to_numpy(np.int64)
        o, hh, ll, c, v = (g[k].to_numpy(float) for k in "ohlcv")
        prev = np.concatenate([[g1["c"].iloc[0]], g1["c"].to_numpy()[:-1]])
        tr = np.maximum(g1["h"].to_numpy(), prev) - \
            np.minimum(g1["l"].to_numpy(), prev)
        natr24 = pd.Series(tr).rolling(24).mean().to_numpy() / g1["c"].to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v,
                           natr_t=(g1["t"] + H).to_numpy(), natr=natr24)
    return tickers


LADDER = [
    ("Super Monk  (4%/1x both, flat)",
     dict(S=(0.04, 1, 0.0, 0.08), C=(0.04, 1, 0.0, 0.08))),
    ("Super Eddie (20%/1x both, flat)",
     dict(S=(0.20, 1, 0.0, 0.20), C=(0.20, 1, 0.0, 0.20))),
    ("Super Harry (S 25%/2x quad c50, C 25%/1x)",
     dict(S=(0.25, 2, 2.0, 0.50), C=(0.25, 1, 1.0, 0.50))),
    ("SUPER LARRY — FINAL SPEC (S 25%/3x quad c50, C 25%/2x lin c30)",
     dict(S=(0.25, 3, 2.0, 0.50), C=(0.25, 2, 1.0, 0.30))),
    ("Super Larry MAX (S 35%/3x quad c75, C 35%/2x lin c75)",
     dict(S=(0.35, 3, 2.0, 0.75), C=(0.35, 2, 1.0, 0.75))),
]


def run_ladder(tag, tickers, dial, regime_at, chain):
    p(f"  [{tag}] {len(tickers)} tickers")
    p(f"  {'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>5s} {'C':>5s} "
      f"{'skip':>6s} {'liq':>4s}")
    for name, cfg in LADDER:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at, cfg)
        p(f"  {name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")
        chain[(tag, name)] = eq / START
    cfg = LADDER[3][1]
    for legs, nm in [(("S",), "  -> leg S alone (Larry sizing)"),
                     (("C",), "  -> leg C alone (Larry sizing)")]:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at,
                                                  cfg, legs=legs)
        p(f"  {nm:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"SUPER LARRY, FULL UNIVERSE — {stamp}")
    p("wide cache = every USDT perp ever listed (delisted incl.), merged "
      "with curated 60; same ladder/machinery as super_larry.py")
    p("")

    chain = {}
    tags_by_track = []
    for label, c15, c1 in [
        ("2023-24 bear", "backtest/r60_oos_15m.csv.gz",
         "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main", "backtest/r60_candles_15m.csv.gz",
         "backtest/r60_candles_1h.csv.gz"),
    ]:
        curated, regime_at = load(c15, c1)
        t_lo = int(min(d["t"][0] for d in curated.values()))
        t_hi = int(max(d["t"][-1] for d in curated.values()))
        p("=" * 104)
        p(f"TRACK: {label}  ({pd.to_datetime(t_lo, unit='ms').date()} .. "
          f"{pd.to_datetime(t_hi, unit='ms').date()})")
        for d in curated.values():
            precompute(d)
        ev = pump_events(curated)
        dial_cur = make_dial(*ev, WDAYS, THR)
        p(f"  curated pump events: {len(ev[0]):,}")
        run_ladder(f"{label} CURATED", curated, dial_cur, regime_at, chain)
        p("")

        wide = load_wide_era(t_lo, t_hi, skip=set(curated))
        full = dict(curated)
        full.update(wide)
        for d in wide.values():
            precompute(d)
        ev = pump_events(full)
        dial_full = make_dial(*ev, WDAYS, THR)
        p(f"  +{len(wide)} expansion tickers | full-universe pump events: "
          f"{len(ev[0]):,}")
        run_ladder(f"{label} FULL", full, dial_full, regime_at, chain)
        p("")
        tags_by_track.append((f"{label} CURATED", f"{label} FULL"))
        del curated, wide, full, ev
        gc.collect()

    p("CHAINED $10k, 2023 -> Oct 2026:")
    p(f"  {'config':52s} {'CURATED 60':>14s} {'FULL UNIVERSE':>14s}")
    for name, _ in LADDER:
        cur = START
        ful = START
        for tag_c, tag_f in tags_by_track:
            cur *= chain[(tag_c, name)]
            ful *= chain[(tag_f, name)]
        p(f"  {name:52s} ${cur:>13,.0f} ${ful:>13,.0f}")

    fname = ("reports/super_larry_wide_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
