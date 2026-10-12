#!/usr/bin/env python3
"""GRAND FINALE — the tuned winner behind the regime gate, full 2023-2026.

Tuned winner: base signals, 24h hold, 3x lev, margin = 35% x (runup/12%)^2
capped at 75% of equity, stop = 4h high, max 4 concurrent.
Gate: the fleet's gate30 dial — trailing 30d mean 24h fwd return of completed
pump events; shorts allowed only while the dial is negative (same mechanics
as regime_switch_backtest / the live fleet).

Runs gated vs ungated on the 2023-24 bear track and the 2025-26 main track,
then chains $10k through the whole four years.

Usage: python3 grand_finale.py
Writes: reports/grand_finale_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load
from degen_derby import precompute, sig_pump, resolve, START
from regime_switch_backtest import pump_events, make_dial
from backtest import M15

LEV, BASE, POW, CAP, HOLD, CONC = 3, 0.35, 2.0, 0.75, 96, 4
WDAYS, THR = 30, 0.0

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def run_track(tickers, dial, gated, start_eq):
    sigs = []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        sigs += [(d["t"][i] + M15, tk, i) for i in ii]
    sigs.sort()
    eq, peak, maxdd = start_eq, start_eq, 0.0
    pending, open_until = [], {}
    trades = skipped = liqs = 0
    monthly = {}
    for t_sig, tk, i in sigs:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl, lq = pending.pop(0)
            eq += pnl
            liqs += lq
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq < start_eq * 0.001:
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= CONC:
            continue
        if gated and dial(t_sig)[0] != -1:
            skipped += 1
            continue
        d = tickers[tk]
        net, exit_t, kind = resolve(d, i, "short", HOLD, "4hhigh", LEV)
        ru = d["runup_v"][i]
        frac = min(BASE * (ru / 0.12) ** POW, CAP)
        margin = min(frac * eq, eq)
        pnl = max(margin * LEV * net, -margin)
        pending.append((exit_t, pnl, kind == "LIQUIDATED"))
        open_until[tk] = exit_t
        trades += 1
    for et, pnl, lq in sorted(pending):
        eq += pnl
        liqs += lq
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    return max(eq, 0.0), maxdd, trades, skipped, liqs


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"GRAND FINALE — {stamp}")
    p(f"tuned winner (24h hold, {LEV}x, 35% x (runup/12%)^2 cap 75%) | gate30 dial "
      f"(trailing {WDAYS}d mean 24h fwd return of pump events, short iff < {THR})")
    p("")

    tracks = []
    for label, c15, c1 in [
        ("2023-24 bear track", "backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main track", "backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz"),
    ]:
        tickers, _ = load(c15, c1)
        for d in tickers.values():
            precompute(d)
        ev_t, ev_r, ev_done = pump_events(tickers)
        dial = make_dial(ev_t, ev_r, ev_done, WDAYS, THR)
        tracks.append((label, tickers, dial, len(ev_t)))

    p(f"{'track':22s} {'mode':8s} {'$10k ->':>14s} {'maxdd':>8s} {'trades':>7s} {'skipped':>8s} {'liqs':>5s}")
    chain = {}
    for label, tickers, dial, nev in tracks:
        for gated in (False, True):
            eq, maxdd, trades, skipped, liqs = run_track(tickers, dial, gated, START)
            mode = "GATED" if gated else "ungated"
            p(f"{label:22s} {mode:8s} ${eq:>13,.0f} {maxdd*100:7.1f}% {trades:7d} {skipped:8d} {liqs:5d}")
            chain[(label, gated)] = eq / START
        p("")

    p("CHAINED $10k THROUGH ALL FOUR YEARS (2023 -> Oct 2026):")
    for gated in (False, True):
        total = START
        for label, *_ in tracks:
            total *= chain[(label, gated)]
        p(f"  {'GATED' if gated else 'ungated':8s} ${total:,.0f}")

    fname = f"reports/grand_finale_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
