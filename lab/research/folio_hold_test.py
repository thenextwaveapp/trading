#!/usr/bin/env python3
"""FOLIO HOLD COMPARISON — current folio (all books 24h) vs long books at
48h vs everything at 48h. Same machinery as folio_backtest.py, Invo 60,
2025-26 window.

Usage: python3 research/folio_hold_test.py
Writes: reports/folio_hold_<stamp>.txt
"""
from datetime import datetime, timezone

from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
from fleet_race import sig_pump_rows, sig_capit_rows, sig_hourly_rows
from folio_backtest import run_folio, MAJORS

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def folio_rows_h(tickers, dial, regime_at, h_capit, h_loser, h_short):
    majors = {tk: d for tk, d in tickers.items() if tk in MAJORS}
    books = [
        ("capit_invo", 1.0, 3, False,
         sig_capit_rows(tickers, dict(depth=0.20, hold=h_capit,
                                      btc_bear=True, stop=("none", 0)),
                        regime_at)),
        ("capit_maj", 1.0, 2, False,
         sig_capit_rows(majors, dict(depth=0.20, hold=h_capit,
                                     btc_bear=False, stop=("none", 0)),
                        regime_at)),
        ("short_hold24", 0.5, 4, False,
         sig_pump_rows(tickers, dict(runup=0.12, vol=2.0, hold=h_short,
                                     stop=("hh", 0.0), gate=True), dial)),
        ("loser3_maj", 0.5, 8, True,
         sig_hourly_rows(majors, dict(engine="loser", min_move=0.03,
                                      hold=h_loser, every=4, slots=8))),
    ]
    rows = []
    for bname, w, cap, reentry, brows in books:
        for t_sig, tk, tr in brows:
            rows.append((t_sig, tk, dict(tr, book=bname, risk_w=w,
                                         cap=cap, reentry=reentry)))
    rows.sort(key=lambda r: r[0])
    return rows


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FOLIO HOLD COMPARISON — {stamp} | Invo 60, 2025-26")
    p("")
    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)

    arms = [
        ("current (all books 24h)", 96, 96, 96),
        ("longs 48h, short 24h", 192, 192, 96),
        ("everything 48h", 192, 192, 192),
    ]
    p(f"{'arm':26s} {'$10k ->':>11s} {'ret%':>8s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg':>7s}")
    for name, hc, hl, hs in arms:
        rows = folio_rows_h(tickers, dial, regime_at, hc, hl, hs)
        eq, maxdd, n, avg, win, by_book = run_folio(tickers, rows)
        p(f"{name:26s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
          f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+6.2f}%")
        for b, (cnt, pnl) in by_book.items():
            p(f"    {b:16s} {cnt:4d} trades  pnl ${pnl:+,.0f}")
        p("")

    fname = ("reports/folio_hold_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
