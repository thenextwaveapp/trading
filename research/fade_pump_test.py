#!/usr/bin/env python3
"""FADE_PUMP TEST — short the universe's biggest 1h winner (>= +6%),
excluding the top-10 by dollar volume; BTC-bull blocks entry; gate30 dial
must read short. Hold 3h, stop +1.8%, TP -4.5%. Fleet account model.

Arms: spec | no TP (stop+time only) | ungated (no dial, no BTC filter).
Tracks: 2023-24 bear and 2025-26 main, Invo 60.

Usage: python3 research/fade_pump_test.py
Writes: reports/fade_pump_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from backtest import M15
from rules_backtest import load, TAKER, SLIP
from wf_engine import RISK, NOTIONAL_CAP, KILL_DD, KILL_LOOKBACK, KILL_PAUSE
from degen_derby import START
from regime_switch_backtest import pump_events, make_dial

COST = 2 * TAKER + SLIP
STOP, TP, HOLD, MIN_MV, CONC = 0.018, 0.045, 12, 0.06, 4

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def resolve(d, i, use_tp):
    t, h, l, c = d["t"], d["h"], d["l"], d["c"]
    entry = c[i]
    sl, tp = entry * (1 + STOP), entry * (1 - TP)
    end = min(i + HOLD, len(t) - 1)
    for j in range(i + 1, end + 1):
        if h[j] >= sl:
            return -STOP - COST, t[j] + M15, "sl"
        if use_tp and l[j] <= tp:
            return TP - COST, t[j] + M15, "tp"
    return -(c[end] / entry - 1) - COST, t[end] + M15, "time"


def run(tickers, rows, dial, regime_at, gated, use_tp):
    eq, peak, maxdd = START, START, 0.0
    eq_hist, pending, open_until, kill_until = [], [], {}, 0
    nets, wins, kinds = [], 0, {}
    for t_sig, tk, i in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            eq += pnl
            eq_hist.append((et, eq))
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if gated:
            if dial(t_sig)[0] != -1:
                continue
            if regime_at(t_sig) is True:      # BTC bull blocks
                continue
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= CONC:
            continue
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and eq / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        net, exit_t, kind = resolve(tickers[tk], i, use_tp)
        notional = min(RISK * eq / STOP, NOTIONAL_CAP * eq)
        pending.append((exit_t, notional * net))
        open_until[tk] = exit_t
        nets.append(net)
        wins += net > 0
        kinds[kind] = kinds.get(kind, 0) + 1
    for et, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    n = len(nets)
    return eq, maxdd, n, (np.mean(nets) if n else float("nan")), \
        (wins / n if n else float("nan")), kinds


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FADE_PUMP TEST — {stamp}")
    p(f"short biggest non-top10 1h winner >= +{MIN_MV:.0%} | hold 3h | "
      f"stop +{STOP:.1%} | tp -{TP:.1%} | gate30 dial + BTC-bull block | "
      "fleet sizing (stop-dist risk, conc 4)")
    p("")
    for label, c15, c1 in [
        ("2023-24 bear", "backtest/r60_oos_15m.csv.gz",
         "backtest/r60_oos_1h.csv.gz"),
        ("2025-26 main", "backtest/r60_candles_15m.csv.gz",
         "backtest/r60_candles_1h.csv.gz"),
    ]:
        tickers, regime_at = load(c15, c1)
        dv = {tk: float(np.median(d["c"] * d["v"]))
              for tk, d in tickers.items()}
        top10 = set(sorted(dv, key=dv.get, reverse=True)[:10])
        ev = pump_events(tickers)
        dial = make_dial(*ev, 30, 0.0)
        # candidates: biggest qualifying 1h winner per bar
        cands = {}
        for tk, d in tickers.items():
            if tk in top10:
                continue
            t, h, l, c, v = (d[k] for k in "thlcv")
            for i in range(5, len(t) - 1):
                if t[i] - t[i - 4] != 4 * M15:
                    continue
                if (v[i - 4:i + 1] <= 0).any() or h[i] == l[i]:
                    continue
                mv = c[i] / c[i - 4] - 1
                if mv >= MIN_MV:
                    prev = cands.get(t[i])
                    if prev is None or mv > prev[0]:
                        cands[t[i]] = (mv, tk, i)
        rows = [(ts + M15, tk, i) for ts, (mv, tk, i) in sorted(cands.items())]
        p(f"TRACK {label}: {len(rows):,} candidate signals "
          f"(top10 excluded: {' '.join(sorted(top10))})")
        p(f"  {'arm':18s} {'$10k ->':>11s} {'ret%':>7s} {'maxdd':>7s} "
          f"{'trades':>6s} {'win%':>5s} {'avg':>7s}  exits")
        for arm, gated, use_tp in [("spec", True, True),
                                   ("no TP", True, False),
                                   ("ungated", False, True)]:
            eq, maxdd, n, avg, win, kinds = run(
                tickers, rows, dial, regime_at, gated, use_tp)
            ks = " ".join(f"{k}:{v}" for k, v in sorted(kinds.items()))
            p(f"  {arm:18s} ${eq:>10,.0f} {(eq/START-1)*100:+6.1f}% "
              f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+6.2f}%  {ks}")
        p("")

    fname = ("reports/fade_pump_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
