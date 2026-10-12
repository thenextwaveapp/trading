#!/usr/bin/env python3
"""SOFT GATE — gate the SIZE, not the trade. The closer.

Same tuned winner (24h hold, 3x, quadratic runup sizing), but the margin
budget scales with the gate30 dial instead of switching on/off:

  dial m < -2%          -> full greed  (base 35%, cap 75%)
  -2% <= m < 0          -> half size   (base 17.5%, cap 40%)
  0 <= m < +2% or n<10  -> Monk size   (base 4%, cap 8%)
  m >= +2%              -> flat        (skip)

Compared against: ungated, hard gate (trade iff m<0), on both tracks,
chained 2023 -> Oct 2026.

Usage: python3 soft_gate.py
Writes: reports/soft_gate_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, sig_pump, resolve, START
from regime_switch_backtest import pump_events, make_dial
from backtest import M15

LEV, POW, HOLD, CONC = 3, 2.0, 96, 4
WDAYS, THR = 30, 0.0

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def size_policy(policy, dial, T):
    """Returns (base, cap) margin budget, or None to skip."""
    s, n, m = dial(T)
    if policy == "ungated":
        return 0.35, 0.75
    if policy == "hard":
        return (0.35, 0.75) if s == -1 else None
    # soft
    if np.isnan(m) or n < 10:
        return 0.04, 0.08
    if m < -0.02:
        return 0.35, 0.75
    if m < 0:
        return 0.175, 0.40
    if m < 0.02:
        return 0.04, 0.08
    return None


def run_track(tickers, dial, policy, start_eq):
    sigs = []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        sigs += [(d["t"][i] + M15, tk, i) for i in ii]
    sigs.sort()
    eq, peak, maxdd = start_eq, start_eq, 0.0
    pending, open_until = [], {}
    trades = skipped = small = full = 0
    for t_sig, tk, i in sigs:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            eq += pnl
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq < start_eq * 0.001:
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= CONC:
            continue
        sz = size_policy(policy, dial, t_sig)
        if sz is None:
            skipped += 1
            continue
        base, cap = sz
        if base >= 0.35:
            full += 1
        else:
            small += 1
        d = tickers[tk]
        net, exit_t, kind = resolve(d, i, "short", HOLD, "4hhigh", LEV)
        ru = d["runup_v"][i]
        frac = min(base * (ru / 0.12) ** POW, cap)
        margin = min(frac * eq, eq)
        pnl = max(margin * LEV * net, -margin)
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades += 1
    for et, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    return max(eq, 0.0), maxdd, trades, skipped, full, small


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"SOFT GATE — {stamp} | tuned winner, margin budget scaled by dial strength")
    p("dial m: <-2% full (35/75) | -2..0 half (17.5/40) | 0..+2% monk (4/8) | >+2% flat")
    p("")
    tracks = []
    for label, c15, c1 in [
        ("2023-24 bear track", "backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main track", "backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz"),
    ]:
        tickers, _ = load(c15, c1)
        for d in tickers.values():
            precompute(d)
        ev = pump_events(tickers)
        tracks.append((label, tickers, make_dial(*ev, WDAYS, THR)))

    p(f"{'track':22s} {'policy':9s} {'$10k ->':>14s} {'maxdd':>8s} {'trades':>7s} "
      f"{'(full/small)':>12s} {'skipped':>8s}")
    chain = {}
    for label, tickers, dial in tracks:
        for policy in ("ungated", "hard", "soft"):
            eq, maxdd, trades, skipped, full, small = run_track(tickers, dial, policy, START)
            p(f"{label:22s} {policy:9s} ${eq:>13,.0f} {maxdd*100:7.1f}% {trades:7d} "
              f"{f'{full}/{small}':>12s} {skipped:8d}")
            chain[(label, policy)] = eq / START
        p("")

    p("CHAINED $10k, 2023 -> Oct 2026:")
    for policy in ("ungated", "hard", "soft"):
        total = START
        for label, *_ in tracks:
            total *= chain[(label, policy)]
        p(f"  {policy:9s} ${total:,.0f}")

    fname = f"reports/soft_gate_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
