#!/usr/bin/env python3
"""DERBY HEATS — four follow-up races to the Degen Derby.

A. SURVIVOR BRACKET — podium sizing dropped onto the 2023-24 bear track
   (where buying pumps worked and shorting them lost).
B. LEVERAGE CLIFF — frozen rule, 25% margin, leverage 1x..8x. Where does
   Larry become Dave?
C. PARALLEL UNIVERSES — same 163 trade outcomes, order shuffled 2000x,
   Larry sizing. How lucky was the trophy?
D. GALAXY BRAIN SIZING — bet more on bigger pumps vs flat vs the reverse.

Usage: python3 derby_heats.py
Writes: reports/derby_heats_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load
from degen_derby import precompute, sig_pump, sig_chase, resolve, race, COST, START
from backtest import M15

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def show(r, k=None):
    tag = " 💀BUSTED" if r["busted"] else (f" ⚡{r['liqs']}liq" if r["liqs"] else "")
    pre = f"{k+1:2d}. " if k is not None else "  "
    p(f"  {pre}{r['name']:46s} ${r['final']:>12,.0f}  ({r['ret']*100:+9.1f}%)  "
      f"trades {r['trades']:4d}  win {r['win']*100:4.1f}%  dd {r['maxdd']*100:6.1f}%{tag}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"DERBY HEATS — {stamp}")
    p("")

    # ================================================= A. survivor bracket
    p("=" * 100)
    p("HEAT A: SURVIVOR BRACKET — same racers, 2023-24 bear track (out-of-regime)")
    p("=" * 100)
    oos, _ = load("backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz")
    for d in oos.values():
        precompute(d)
    tmin = min(d["t"][0] for d in oos.values())
    tmax = max(d["t"][-1] for d in oos.values())
    f = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    p(f"track: {f(tmin)} -> {f(tmax)} | {len(oos)} tickers")
    bracket = [
        ("Leverage Larry (25% at 4x)", sig_pump, dict(), 16, "4hhigh", 0.25, 4, 4, False),
        ("Full Port Frank (100%, no lev)", sig_pump, dict(), 16, "4hhigh", 1.00, 1, 1, False),
        ("Wide-Boy Wes (buf2, 40% 2x)", sig_pump, dict(), 16, "buf2", 0.40, 2, 3, False),
        ("Half-Port Harry (50%)", sig_pump, dict(), 16, "4hhigh", 0.50, 1, 4, False),
        ("Steady Eddie (20%)", sig_pump, dict(), 16, "4hhigh", 0.20, 1, 6, False),
        ("The Monk (by the book)", sig_pump, dict(), 16, "4hhigh", 0.04, 1, 6, False),
        ("The Chaser (buys pumps, 50%) — redemption?", sig_chase, dict(), 16, "tight", 0.50, 1, 3, False),
    ]
    res = []
    for name, sg, kw, hold, stop, frac, lev, conc, mart in bracket:
        res.append(race(name, oos, sg, kw, hold, stop, frac, lev, conc, mart))
    res.sort(key=lambda r: r["final"], reverse=True)
    for k, r in enumerate(res):
        show(r, k)
    p("")

    # ================================================= B. leverage cliff
    p("=" * 100)
    p("HEAT B: THE LEVERAGE CLIFF — frozen rule, 25% margin, lev 1x..8x, main track")
    p("=" * 100)
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    for lev in range(1, 9):
        r = race(f"25% margin at {lev}x (notional {int(25*lev)}% eq/trade)",
                 tickers, sig_pump, dict(), 16, "4hhigh", 0.25, lev, 4, False)
        show(r)
    p("")

    # ================================================= C. parallel universes
    p("=" * 100)
    p("HEAT C: PARALLEL UNIVERSES — Larry's 163 trades, order shuffled 2000x")
    p("=" * 100)
    df = pd.read_csv("backtest/derby_base_trades.csv").sort_values("t")
    nets = df["net"].to_numpy()
    FRAC, LEV = 0.25, 4

    def run_seq(seq):
        eq = START
        for net in seq:
            pnl = max(eq * FRAC * LEV * net, -eq * FRAC)
            eq += pnl
            if eq < START * 0.01:
                return 0.0
        return eq

    actual = run_seq(nets)
    rng = np.random.default_rng(42)
    finals = np.array([run_seq(rng.permutation(nets)) for _ in range(2000)])
    p(f"  actual order:   ${actual:,.0f}   (sequential approx of Larry's rig)")
    p(f"  2000 universes: median ${np.median(finals):,.0f} | "
      f"p5 ${np.percentile(finals,5):,.0f} | p95 ${np.percentile(finals,95):,.0f}")
    p(f"  busted (<1% of start): {(finals <= START*0.01).mean()*100:.1f}% of universes")
    p(f"  ended below $10k start: {(finals < START).mean()*100:.1f}%")
    p(f"  ended below the Monk ($11.4k): {(finals < 11388).mean()*100:.1f}%")
    p(f"  beat the actual-order result: {(finals > actual).mean()*100:.1f}%")
    p("")

    # ================================================= D. galaxy brain sizing
    p("=" * 100)
    p("HEAT D: GALAXY BRAIN SIZING — scale the bet to the pump, lev 4x, conc 4")
    p("=" * 100)

    def race_sized(name, frac_fn):
        rows = []
        for tk, d in tickers.items():
            ii, _ = sig_pump(d)
            rows += [(d["t"][i] + M15, tk, i) for i in ii]
        rows.sort()
        eq, peak, maxdd = START, START, 0.0
        pending, open_until = [], {}
        trades = wins = liqs = 0
        for t_sig, tk, i in rows:
            pending.sort()
            while pending and pending[0][0] <= t_sig:
                et, pnl, won, lq = pending.pop(0)
                eq += pnl
                wins += won
                liqs += lq
                peak = max(peak, eq)
                maxdd = min(maxdd, eq / peak - 1)
            if eq < START * 0.01:
                break
            if open_until.get(tk, 0) > t_sig:
                continue
            if sum(1 for x in open_until.values() if x > t_sig) >= 4:
                continue
            d = tickers[tk]
            net, exit_t, kind = resolve(d, i, "short", 16, "4hhigh", 4)
            frac = frac_fn(d["runup_v"][i])
            margin = min(frac * eq, eq)
            pnl = max(margin * 4 * net, -margin)
            pending.append((exit_t, pnl, net > 0, kind == "LIQUIDATED"))
            open_until[tk] = exit_t
            trades += 1
        for et, pnl, won, lq in sorted(pending):
            eq += pnl
            wins += won
            liqs += lq
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        eq = max(eq, 0.0)
        p(f"  {name:46s} ${eq:>12,.0f}  ({eq/START*100-100:+9.1f}%)  "
          f"trades {trades:4d}  dd {maxdd*100:6.1f}%  liqs {liqs}")

    race_sized("FLAT 25% (Larry control)", lambda ru: 0.25)
    race_sized("scaled: frac = 25% x (runup/12%), cap 60%", lambda ru: min(0.25 * ru / 0.12, 0.60))
    race_sized("scaled hard: frac = 25% x (runup/12%)^2, cap 75%", lambda ru: min(0.25 * (ru / 0.12) ** 2, 0.75))
    race_sized("anti-scaled: frac = 25% x (12%/runup), cap 60%", lambda ru: min(0.25 * 0.12 / ru, 0.60))
    race_sized("monsters only: 0 if runup<20%, else 50%", lambda ru: 0.50 if ru >= 0.20 else 0.0)

    fname = f"reports/derby_heats_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
