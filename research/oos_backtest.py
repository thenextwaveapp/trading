#!/usr/bin/env python3
"""Out-of-sample run: all 9 live-fleet variants on 2023-01 -> 2024-12 — a
period no prior analysis in this project ever touched. Same portfolio and
fee model as rules_backtest.py; 8 quarterly windows.

Known bias to keep in mind when reading results: the 60-ticker universe was
selected by Invo trade count in 2026, so tickers that died before 2026 are
missing and several (HYPE, PUMP, FARTCOIN, PENGU, TRUMP, KAITO, ...) did not
exist yet in 2023-24 — the tradable universe here is smaller and more
major-heavy than in the 2025-26 windows.

Usage: python3 oos_backtest.py
Writes: reports/oos_backtest_<stamp>.txt, backtest/trades_oos.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics
from rules_backtest import load
from variants_backtest import signals_v
from holds_stops_backtest import exit_g, portfolio
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from runtime.paper_fleet import VARIANTS

OOS_WINDOWS = [
    ("2023Q1", "2023-01-01", "2023-04-01"),
    ("2023Q2", "2023-04-01", "2023-07-01"),
    ("2023Q3", "2023-07-01", "2023-10-01"),
    ("2023Q4", "2023-10-01", "2024-01-01"),
    ("2024Q1", "2024-01-01", "2024-04-01"),
    ("2024Q2", "2024-04-01", "2024-07-01"),
    ("2024Q3", "2024-07-01", "2024-10-01"),
    ("2024Q4", "2024-10-01", "2024-12-15"),
]

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def exit_cfg(cfg):
    """Map a fleet variant config to holds_stops_backtest.exit_g's format."""
    mode, parm = cfg["stop"]
    if mode == "hh":
        return dict(hold=cfg["hold"], stop="hh", buf=parm)
    return dict(hold=cfg["hold"], stop=mode, k=parm)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz")
    p(f"OUT-OF-SAMPLE VARIANTS — {stamp} | 2023-01 -> 2024-12 | "
      f"{len(tickers)} tickers with data | fresh period, zero prior contact")

    sig_groups = {}
    for name, cfg in VARIANTS.items():
        sig_groups.setdefault((cfg["runup"], cfg["vol"]), []).append(name)

    all_rows, win_stats = [], {n: [] for n in VARIANTS}
    for wname, a, b in OOS_WINDOWS:
        t0, t1 = ts(a), ts(b)
        for (runup_min, vol_min), names in sig_groups.items():
            rows = []
            for tk, d in tickers.items():
                rows += [(tsg, tk, i, ru)
                         for tsg, i, ru in signals_v(d, t0, t1, runup_min, vol_min)]
            for name in names:
                ecfg = exit_cfg(VARIANTS[name])
                trades, eqh = portfolio(rows, tickers, ecfg)
                met = metrics(eqh, t0, t1)
                nets = [x["net"] for x in trades]
                p(f"{wname} {name:8s}: trades {len(trades):3,} | "
                  f"net/trade {np.mean(nets)*100 if nets else 0:+.3f}% | "
                  f"eq {met['ret']*100:+.2f}% dd {met['maxdd']*100:.2f}%")
                for x in trades:
                    x.update(window=wname, variant=name)
                all_rows += trades
                win_stats[name].append(dict(window=wname, n=len(trades),
                                            net=np.mean(nets) if nets else np.nan,
                                            ret=met["ret"], dd=met["maxdd"]))
    t = pd.DataFrame(all_rows)
    t.to_csv("backtest/trades_oos.csv.gz", index=False, compression="gzip")
    p("")
    p("=" * 100)
    p("SUMMARY 2023-2024 (gate criteria for reference; low-trade windows (<10) excluded from windows+,")
    p("per the pre-registered low-count amendment)")
    p(f"{'variant':8s} {'trades':>6s} {'net/trade':>9s} {'win%':>5s} {'sl%':>4s} "
      f"{'windows+':>8s} {'compounded':>10s} {'worst dd':>8s} {'top-tkr':>7s}  gate")
    for name in VARIANTS:
        g = t[t["variant"] == name]
        ws = pd.DataFrame(win_stats[name]).dropna(subset=["net"])
        if not len(g):
            p(f"{name:8s} no trades")
            continue
        pooled = g["net"].mean()
        winr = (g["net"] > 0).mean() * 100
        slr = (g["kind"] == "sl").mean() * 100
        eqs = (1 + ws["ret"]).prod() - 1
        conc = g.groupby("ticker")["pnl"].sum()
        pos = conc[conc > 0].sum()
        top = conc.max() / pos * 100 if pos > 0 else np.nan
        wsq = ws[ws["n"] >= 10]
        winpos = (wsq["ret"] > 0).mean() * 100 if len(wsq) else np.nan
        checks = [pooled >= 0.0010,
                  (winpos >= 60) if len(wsq) else True,
                  ws["dd"].min() >= -0.20, top <= 40]
        wstr = f"{winpos:7.0f}%" if len(wsq) else "   n<10"
        p(f"{name:8s} {len(g):6,} {pooled*100:+8.3f}% {winr:4.0f}% {slr:3.0f}% "
          f"{wstr} {eqs*100:+9.2f}% {ws['dd'].min()*100:7.1f}% {top:6.0f}%  "
          f"{'pass' if all(checks) else 'fail'} ({sum(checks)}/4)")
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/oos_backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
