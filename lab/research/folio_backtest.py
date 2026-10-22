#!/usr/bin/env python3
"""FOLIO BACKTEST — the four-book portfolio variant vs the best single
variants, Invo 60, 2025-26 main window. Books and account rules mirror
paper_fleet.run_books: shared $10k, per-book caps and risk weights, one
position per ticker account-wide (loser book may re-enter its own ticker),
account-level kill-switch, standard risk sizing.

Usage: python3 research/folio_backtest.py
Writes: reports/folio_backtest_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from wf_engine import RISK, NOTIONAL_CAP, KILL_DD, KILL_LOOKBACK, KILL_PAUSE
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
from fleet_race import (sig_pump_rows, sig_capit_rows, sig_hourly_rows,
                        resolve_trade, race)

MAJORS = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK",
          "AVAX", "LTC"}

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def folio_rows(tickers, dial, regime_at):
    majors = {tk: d for tk, d in tickers.items() if tk in MAJORS}
    books = [
        ("capit_invo", 1.0, 3, False,
         sig_capit_rows(tickers, dict(depth=0.20, hold=96, btc_bear=True,
                                      stop=("none", 0)), regime_at)),
        ("capit_maj", 1.0, 2, False,
         sig_capit_rows(majors, dict(depth=0.20, hold=96, btc_bear=False,
                                     stop=("none", 0)), regime_at)),
        ("short_hold24", 0.5, 4, False,
         sig_pump_rows(tickers, dict(runup=0.12, vol=2.0, hold=96,
                                     stop=("hh", 0.0), gate=True), dial)),
        ("loser3_maj", 0.5, 8, True,
         sig_hourly_rows(majors, dict(engine="loser", min_move=0.03,
                                      hold=96, every=4, slots=8))),
    ]
    rows = []
    for bname, w, cap, reentry, brows in books:
        for t_sig, tk, tr in brows:
            rows.append((t_sig, tk, dict(tr, book=bname, risk_w=w,
                                         cap=cap, reentry=reentry)))
    rows.sort(key=lambda r: r[0])
    return rows


def run_folio(tickers, rows):
    eq, peak, maxdd = START, START, 0.0
    eq_hist, pending, kill_until = [], [], 0
    open_pos = []                       # (ticker, book, exit_t)
    nets, wins, by_book = [], 0, {}
    for t_sig, tk, tr in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            eq += pnl
            eq_hist.append((et, eq))
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        open_pos = [x for x in open_pos if x[2] > t_sig]
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and eq / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        b = tr["book"]
        held = {x[0] for x in open_pos
                if not (tr["reentry"] and x[1] == b)}
        if tk in held:
            continue
        if sum(1 for x in open_pos if x[1] == b) >= tr["cap"]:
            continue
        d = tickers[tk]
        net, exit_t, kind = resolve_trade(d, tr)
        if tr["sizing"] == "slots":
            notional = tr["risk_w"] * eq / tr["cap"]
        else:
            sl_dist = tr.get("sl_dist")
            if sl_dist is None:
                sl_dist = abs(tr["stop"] / tr["entry"] - 1) if tr["stop"] \
                    else 0.005
            notional = tr["risk_w"] * min(RISK * eq / max(abs(sl_dist), 0.005),
                                          NOTIONAL_CAP * eq)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_pos.append((tk, b, exit_t))
        nets.append(net)
        wins += net > 0
        s = by_book.setdefault(b, [0, 0.0])
        s[0] += 1
        s[1] += pnl
    for et, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    n = len(nets)
    return eq, maxdd, n, (np.mean(nets) if n else float("nan")), \
        (wins / n if n else float("nan")), by_book


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FOLIO BACKTEST — {stamp} | Invo 60, 2025-26 main window")
    p("folio books mirror paper_fleet.run_books; rivals at fleet sizing")
    p("")

    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)
    majors = {tk: d for tk, d in tickers.items() if tk in MAJORS}

    p(f"{'variant':14s} {'$10k ->':>11s} {'ret%':>8s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg net':>8s}")
    eq, maxdd, n, avg, win, by_book = run_folio(
        tickers, folio_rows(tickers, dial, regime_at))
    p(f"{'FOLIO':14s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
      f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+7.2f}%")
    for b, (cnt, pnl) in by_book.items():
        p(f"  {b:16s} {cnt:4d} trades  pnl ${pnl:+,.0f}")
    p("")

    rivals = [
        ("base", tickers, dict(runup=0.12, vol=2.0, hold=16,
                               stop=("hh", 0.0)), "pump"),
        ("hold24", tickers, dict(runup=0.12, vol=2.0, hold=96,
                                 stop=("hh", 0.0)), "pump"),
        ("capit", tickers, dict(depth=0.20, hold=96, btc_bear=True,
                                stop=("none", 0)), "capit"),
        ("capit_maj", tickers, dict(depth=0.20, hold=96, btc_bear=True,
                                    stop=("none", 0),
                                    only=sorted(MAJORS)), "capit"),
        ("loser3", tickers, dict(engine="loser", min_move=0.03, hold=96,
                                 every=4, slots=8,
                                 stop=("none", 0)), "hourly"),
        ("loser3_maj", majors, dict(engine="loser", min_move=0.03, hold=96,
                                    every=4, slots=8,
                                    stop=("none", 0)), "hourly"),
    ]
    for vn, uni, cfg, kind in rivals:
        if kind == "pump":
            rows = sig_pump_rows(uni, cfg, dial)
        elif kind == "capit":
            rows = sig_capit_rows(uni, cfg, regime_at)
        else:
            rows = sig_hourly_rows(uni, cfg)
        eq, maxdd, n, avg, win = race(uni, rows, cfg)
        p(f"{vn:14s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
          f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+7.2f}%")

    fname = ("reports/folio_backtest_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
