#!/usr/bin/env python3
"""FOLIO AT LEVERAGE — same four books, same window, notional x lev on
isolated margin: margin = the 1x notional, loss floored at -margin,
liquidation when the adverse move reaches 1/lev - 0.5% before stop/exit.

Usage: python3 research/folio_lev_backtest.py
Writes: reports/folio_lev_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from backtest import M15
from rules_backtest import load
from wf_engine import RISK, NOTIONAL_CAP, KILL_DD, KILL_LOOKBACK, KILL_PAUSE
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
from fleet_race import COST
from folio_backtest import folio_rows

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def resolve_lev(d, tr, lev):
    i, side, entry = tr["i"], tr["side"], tr["entry"]
    liq = 1.0 / lev - 0.005 if lev > 1 else np.inf
    level, low_min = tr["stop"], entry
    t, h, l, c = d["t"], d["h"], d["l"], d["c"]
    end = min(i + tr["hold"], len(t) - 1)
    for j in range(i + 1, end + 1):
        if (h[j] >= entry * (1 + liq)) if side < 0 else \
                (l[j] <= entry * (1 - liq)):
            return -liq - COST, t[j] + M15, "LIQ"
        if level is not None and level > 0 and \
                ((h[j] > level) if side < 0 else (l[j] < level)):
            return side * (level / entry - 1) - COST, t[j] + M15, "sl"
        if side < 0 and tr.get("trail_k") and tr.get("natr"):
            low_min = min(low_min, l[j])
            level = min(level, low_min * (1 + tr["trail_k"] * tr["natr"]))
    return side * (c[end] / entry - 1) - COST, t[end] + M15, "time"


def run_folio_lev(tickers, rows, lev):
    eq, peak, maxdd = START, START, 0.0
    eq_hist, pending, kill_until = [], [], 0
    open_pos, nets, wins, liqs = [], [], 0, 0
    for t_sig, tk, tr in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            eq += pnl
            eq_hist.append((et, eq))
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq < START * 0.001:
            break
        open_pos = [x for x in open_pos if x[2] > t_sig]
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and eq / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        b = tr["book"]
        held = {x[0] for x in open_pos if not (tr["reentry"] and x[1] == b)}
        if tk in held:
            continue
        if sum(1 for x in open_pos if x[1] == b) >= tr["cap"]:
            continue
        net, exit_t, kind = resolve_lev(tickers[tk], tr, lev)
        if tr["sizing"] == "slots":
            margin = tr["risk_w"] * eq / tr["cap"]
        else:
            sl_dist = tr.get("sl_dist")
            if sl_dist is None:
                sl_dist = abs(tr["stop"] / tr["entry"] - 1) if tr["stop"] \
                    else 0.005
            margin = tr["risk_w"] * min(RISK * eq / max(abs(sl_dist), 0.005),
                                        NOTIONAL_CAP * eq)
        pnl = max(margin * lev * net, -margin)
        pending.append((exit_t, pnl))
        open_pos.append((tk, b, exit_t))
        nets.append(net)
        wins += net > 0
        liqs += kind == "LIQ"
    for et, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    n = len(nets)
    return max(eq, 0.0), maxdd, n, (wins / n if n else float("nan")), liqs


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FOLIO AT LEVERAGE — {stamp} | Invo 60, 2025-26 main window")
    p("same books/rows as folio_backtest; isolated margin, loss floored at "
      "-margin, liq at 1/lev - 0.5%")
    p("")
    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)
    rows = folio_rows(tickers, dial, regime_at)
    p(f"{'lev':>4s} {'$10k ->':>12s} {'ret%':>9s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'liqs':>4s}")
    for lev in (1, 2, 3, 4, 6):
        eq, maxdd, n, win, liqs = run_folio_lev(tickers, rows, lev)
        p(f"{f'{lev}x':>4s} ${eq:>11,.0f} {(eq/START-1)*100:+8.1f}% "
          f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {liqs:4d}")

    fname = ("reports/folio_lev_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
