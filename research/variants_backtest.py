#!/usr/bin/env python3
"""Walk-forward backtest of every paper-fleet pump-short variant over the same
7 windows, portfolio and fee model identical to rules_backtest.py.

Only 'base' is the pre-registered rule; the other variants are exploratory
parameter probes, reported with the same gate criteria for comparison.

Usage: python3 variants_backtest.py
Writes: reports/variants_backtest_<stamp>.txt, backtest/trades_variants.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import WINDOWS, ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, \
    KILL_DD, KILL_LOOKBACK, KILL_PAUSE
from backtest import M15
from rules_backtest import load, alive, TAKER, SLIP
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from paper_fleet import VARIANTS

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def signals_v(d, t0, t1, runup_min, vol_min):
    t, c, v = d["t"], d["c"], d["v"]
    lo = np.searchsorted(t, t0 - M15)
    hi = np.searchsorted(t, t1 - M15)
    out = []
    for i in range(max(lo, 20), hi):
        if not alive(d, i):
            continue
        runup = c[i] / c[i - 16] - 1
        if runup < runup_min or c[i] >= c[i - 1]:
            continue
        mu = v[i - 8:i].mean()
        if mu <= 0 or v[i] / mu < vol_min:
            continue
        out.append((t[i] + M15, i, runup))
    return out


def exit_v(d, i, entry, hold, stop_lb):
    sl_level = d["h"][i - stop_lb:i + 1].max()
    for j in range(i + 1, min(i + hold + 1, len(d["t"]))):
        if d["h"][j] > sl_level:
            gross = -(sl_level / entry - 1)
            return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", (sl_level / entry - 1)
    j = min(i + hold, len(d["t"]) - 1)
    gross = -(d["c"][j] / entry - 1)
    return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "time", (sl_level / entry - 1)


def portfolio(sig_rows, tickers, hold, stop_lb):
    sig_rows = sorted(sig_rows)
    trades, pending, open_until = [], [], {}
    equity, eq_hist, kill_until = 1.0, [], 0
    for t_sig, tk, i, extra in sig_rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            equity += pnl
            eq_hist.append((et, equity))
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= MAX_CONC:
            continue
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and equity / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        d = tickers[tk]
        entry = d["c"][i]
        net, exit_t, kind, sl_dist = exit_v(d, i, entry, hold, stop_lb)
        notional = min(RISK * equity / max(abs(sl_dist), 0.005), NOTIONAL_CAP * equity)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades.append(dict(ticker=tk, t=t_sig, kind=kind, net=net, pnl=pnl, extra=extra))
    for et, pnl in sorted(pending):
        equity += pnl
        eq_hist.append((et, equity))
    return trades, eq_hist


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    p(f"VARIANTS WALK-FORWARD — {stamp} | universe {len(tickers)} tickers | "
      f"{len(VARIANTS)} variants | only 'base' is pre-registered")

    # group variants sharing a signal set so each set is scanned once per window
    sig_groups = {}
    for name, cfg in VARIANTS.items():
        sig_groups.setdefault((cfg["runup"], cfg["vol"]), []).append(name)

    all_rows, win_stats = [], {n: [] for n in VARIANTS}
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        for (runup_min, vol_min), names in sig_groups.items():
            rows = []
            for tk, d in tickers.items():
                rows += [(tsg, tk, i, ru)
                         for tsg, i, ru in signals_v(d, t0, t1, runup_min, vol_min)]
            for name in names:
                cfg = VARIANTS[name]
                trades, eqh = portfolio(rows, tickers, cfg["hold"], cfg["stop_lb"])
                met = metrics(eqh, t0, t1)
                nets = [x["net"] for x in trades]
                p(f"{wname} {name:10s}: signals {len(rows):4,} trades {len(trades):3,} | "
                  f"net/trade {np.mean(nets)*100 if nets else 0:+.3f}% | "
                  f"eq {met['ret']*100:+.2f}% dd {met['maxdd']*100:.2f}%")
                for x in trades:
                    x.update(window=wname, variant=name)
                all_rows += trades
                win_stats[name].append(dict(window=wname, n=len(trades),
                                            net=np.mean(nets) if nets else np.nan,
                                            ret=met["ret"], dd=met["maxdd"]))
    t = pd.DataFrame(all_rows)
    t.to_csv("backtest/trades_variants.csv.gz", index=False, compression="gzip")
    p("")
    p("=" * 94)
    p("SUMMARY (gate criteria shown for all; only 'base' was pre-registered)")
    p(f"{'variant':10s} {'trades':>6s} {'net/trade':>9s} {'win%':>5s} {'windows+':>8s} "
      f"{'compounded':>10s} {'worst dd':>8s} {'top-tkr':>7s}  gate")
    for name in VARIANTS:
        g = t[t["variant"] == name]
        ws = pd.DataFrame(win_stats[name]).dropna(subset=["net"])
        if not len(g):
            p(f"{name:10s} no trades")
            continue
        pooled = g["net"].mean()
        winr = (g["net"] > 0).mean() * 100
        eqs = (1 + ws["ret"]).prod() - 1
        conc = g.groupby("ticker")["pnl"].sum()
        pos = conc[conc > 0].sum()
        top = conc.max() / pos * 100 if pos > 0 else np.nan
        winpos = (ws["ret"] > 0).mean() * 100
        checks = [pooled >= 0.0010, winpos >= 60, ws["dd"].min() >= -0.20, top <= 40]
        p(f"{name:10s} {len(g):6,} {pooled*100:+8.3f}% {winr:4.0f}% {winpos:7.0f}% "
          f"{eqs*100:+9.2f}% {ws['dd'].min()*100:7.1f}% {top:6.0f}%  "
          f"{'pass' if all(checks) else 'fail'} ({sum(checks)}/4)")
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/variants_backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
