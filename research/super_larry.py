#!/usr/bin/env python3
"""SUPER LARRY — the two-leg book: hold24 pump-shorts + capit_slow longs.

Leg S (short):  base pump rule, 24h hold, stop = 4h high, gate30 hard gate
                (trade only while trailing 30d pump-event dial < 0).
Leg C (long):   capitulation — close <= -20% vs 24h ago, 48h hold, no stop (rug risk bounded by margin cap),
                BTC-bear gate (4h EMA20 < EMA50), like the fleet's capit_slow.

One shared account, one position per ticker, shorts conc<=4, capit conc<=3.
Sizing ladder from Monk to tuned greed; each leg also raced alone at Super
Larry sizing to measure the diversification effect. Both tracks + chained.

Usage: python3 super_larry.py
Writes: reports/super_larry_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, sig_pump, sig_capit, resolve, START
from regime_switch_backtest import pump_events, make_dial
from backtest import M15

WDAYS, THR = 30, 0.0

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def run_book(tickers, dial, regime_at, cfg, legs=("S", "C")):
    """cfg: dict with per-leg (frac, lev, pow, cap). Returns summary."""
    rows = []
    for tk, d in tickers.items():
        if "S" in legs:
            ii, _ = sig_pump(d)
            rows += [(d["t"][i] + M15, tk, i, "S") for i in ii]
        if "C" in legs:
            ii, _ = sig_capit(d, drop=0.20)
            rows += [(d["t"][i] + M15, tk, i, "C") for i in ii]
    rows.sort()

    eq, peak, maxdd = START, START, 0.0
    pending, open_until, open_leg = [], {}, {}
    n_s = n_c = skipped = liqs = 0
    for t_sig, tk, i, leg in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl, lq = pending.pop(0)
            eq += pnl
            liqs += lq
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq < START * 0.001:
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        conc = sum(1 for k, x in open_until.items()
                   if x > t_sig and open_leg.get(k) == leg)
        if leg == "S":
            if conc >= 4:
                continue
            if dial(t_sig)[0] != -1:
                skipped += 1
                continue
        else:
            if conc >= 3:
                continue
            if regime_at(t_sig) is not False:   # capit only in BTC bear
                skipped += 1
                continue
        d = tickers[tk]
        frac0, lev, pw, cap = cfg[leg]
        if leg == "S":
            net, exit_t, kind = resolve(d, i, "short", 96, "4hhigh", lev)
            scale = d["runup_v"][i] / 0.12
        else:
            net, exit_t, kind = resolve(d, i, "long", 192, "none", lev)
            scale = -d["drop96_v"][i] / 0.20
        frac = min(frac0 * scale ** pw, cap)
        margin = min(frac * eq, eq)
        pnl = max(margin * lev * net, -margin)
        pending.append((exit_t, pnl, kind == "LIQUIDATED"))
        open_until[tk] = exit_t
        open_leg[tk] = leg
        if leg == "S":
            n_s += 1
        else:
            n_c += 1
    for et, pnl, lq in sorted(pending):
        eq += pnl
        liqs += lq
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    return max(eq, 0.0), maxdd, n_s, n_c, skipped, liqs


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"SUPER LARRY — {stamp} | leg S: hold24 pump-short + gate30 | "
      f"leg C: capit_slow (-20%/24h, 48h hold, no stop, rug bound = C margin cap) + btc-bear gate")
    p("sizing: frac = base x scale^pow (scale = runup/12% or drop/20%), capped; shared account")
    p("")

    tracks = []
    for label, c15, c1 in [
        ("2023-24 bear", "backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main", "backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz"),
    ]:
        tickers, regime_at = load(c15, c1)
        for d in tickers.values():
            precompute(d)
        ev = pump_events(tickers)
        tracks.append((label, tickers, make_dial(*ev, WDAYS, THR), regime_at))

    # ladder: name -> {leg: (base_frac, lev, pow, cap)}
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

    chain = {}
    for label, tickers, dial, regime_at in tracks:
        p("=" * 104)
        p(f"TRACK: {label}")
        p(f"  {'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>4s} {'C':>4s} {'skip':>5s} {'liq':>4s}")
        for name, cfg in LADDER:
            eq, maxdd, n_s, n_c, sk, lq = run_book(tickers, dial, regime_at, cfg)
            p(f"  {name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:4d} {n_c:4d} {sk:5d} {lq:4d}")
            chain[(label, name)] = eq / START
        # diversification check at SUPER LARRY sizing
        cfg = LADDER[3][1]
        for legs, nm in [(("S",), "  -> leg S alone (Larry sizing)"),
                         (("C",), "  -> leg C alone (Larry sizing)")]:
            eq, maxdd, n_s, n_c, sk, lq = run_book(tickers, dial, regime_at, cfg, legs=legs)
            p(f"  {nm:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:4d} {n_c:4d} {sk:5d} {lq:4d}")
        p("")

    p("CHAINED $10k, 2023 -> Oct 2026:")
    for name, _ in LADDER:
        total = START
        for label, *_ in tracks:
            total *= chain[(label, name)]
        p(f"  {name:52s} ${total:,.0f}")

    fname = f"reports/super_larry_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
