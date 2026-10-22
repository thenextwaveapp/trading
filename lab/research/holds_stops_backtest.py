#!/usr/bin/env python3
"""Walk-forward exploration: base pump-short signal (runup >= 12%, vol >= 2x)
with longer hold horizons and stop-rule variations. Exploratory, not
pre-registered; 'base' rows are the anchor for comparison.

Holds (stop = 4h high):      4h (base), 12h, 24h, 48h
Stops (hold = 4h):           4h high +1% / +2% buffer,
                             entry + 1.5x/3x NATR24,
                             trailing: lowest low since entry + 1.5x/3x NATR24,
                             ratcheting down, seeded at the 4h high
Combo:                       24h hold with 3x-NATR trailing stop

Usage: python3 holds_stops_backtest.py
Writes: reports/holds_stops_backtest_<stamp>.txt, backtest/trades_holdstop.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import WINDOWS, ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, \
    KILL_DD, KILL_LOOKBACK, KILL_PAUSE
from backtest import M15
from rules_backtest import load, natr_at, TAKER, SLIP
from variants_backtest import signals_v

CONFIGS = {
    # hold sweep, plain 4h-high stop
    "base_4h":    dict(hold=16,  stop="hh", buf=0.00),
    "hold_12h":   dict(hold=48,  stop="hh", buf=0.00),
    "hold_24h":   dict(hold=96,  stop="hh", buf=0.00),
    "hold_48h":   dict(hold=192, stop="hh", buf=0.00),
    # stop sweep, 4h hold
    "buf1pct":    dict(hold=16,  stop="hh", buf=0.01),
    "buf2pct":    dict(hold=16,  stop="hh", buf=0.02),
    "natr1.5":    dict(hold=16,  stop="natr", k=1.5),
    "natr3":      dict(hold=16,  stop="natr", k=3.0),
    "trail1.5":   dict(hold=16,  stop="trail", k=1.5),
    "trail3":     dict(hold=16,  stop="trail", k=3.0),
    # combo: long hold needs a trailing stop to protect accrued profit
    "24h_trail3": dict(hold=96,  stop="trail", k=3.0),
}

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def exit_g(d, i, entry, cfg):
    hold = cfg["hold"]
    hh = d["h"][i - 16:i + 1].max()
    na = natr_at(d, d["t"][i] + M15)
    if cfg["stop"] == "hh":
        level = hh * (1 + cfg["buf"])
    elif cfg["stop"] == "natr":
        level = entry * (1 + cfg["k"] * na) if na else hh
    else:  # trail — seeded at the 4h high, ratchets down with the lowest low
        level = hh
    init_dist = level / entry - 1
    low_min = entry
    for j in range(i + 1, min(i + hold + 1, len(d["t"]))):
        if d["h"][j] > level:
            gross = -(level / entry - 1)
            return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", init_dist
        if cfg["stop"] == "trail" and na:
            low_min = min(low_min, d["l"][j])
            level = min(level, low_min * (1 + cfg["k"] * na))
    j = min(i + hold, len(d["t"]) - 1)
    gross = -(d["c"][j] / entry - 1)
    return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "time", init_dist


def portfolio(sig_rows, tickers, cfg):
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
        net, exit_t, kind, sl_dist = exit_g(d, i, entry, cfg)
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
    p(f"HOLDS & STOPS WALK-FORWARD — {stamp} | universe {len(tickers)} | "
      f"signal fixed at runup>=12% vol>=2x | exploratory")

    all_rows, win_stats = [], {n: [] for n in CONFIGS}
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i, ru) for tsg, i, ru in signals_v(d, t0, t1, 0.12, 2.0)]
        for name, cfg in CONFIGS.items():
            trades, eqh = portfolio(rows, tickers, cfg)
            met = metrics(eqh, t0, t1)
            nets = [x["net"] for x in trades]
            p(f"{wname} {name:10s}: trades {len(trades):3,} | "
              f"net/trade {np.mean(nets)*100 if nets else 0:+.3f}% | "
              f"eq {met['ret']*100:+.2f}% dd {met['maxdd']*100:.2f}%")
            for x in trades:
                x.update(window=wname, variant=name)
            all_rows += trades
            win_stats[name].append(dict(window=wname, n=len(trades),
                                        net=np.mean(nets) if nets else np.nan,
                                        ret=met["ret"], dd=met["maxdd"]))
    t = pd.DataFrame(all_rows)
    t.to_csv("backtest/trades_holdstop.csv.gz", index=False, compression="gzip")
    p("")
    p("=" * 100)
    p("SUMMARY (same gate criteria for reference; none of these are pre-registered except base_4h)")
    p(f"{'config':10s} {'trades':>6s} {'net/trade':>9s} {'win%':>5s} {'sl%':>4s} "
      f"{'windows+':>8s} {'compounded':>10s} {'worst dd':>8s} {'top-tkr':>7s}  gate")
    for name in CONFIGS:
        g = t[t["variant"] == name]
        ws = pd.DataFrame(win_stats[name]).dropna(subset=["net"])
        if not len(g):
            p(f"{name:10s} no trades")
            continue
        pooled = g["net"].mean()
        winr = (g["net"] > 0).mean() * 100
        slr = (g["kind"] == "sl").mean() * 100
        eqs = (1 + ws["ret"]).prod() - 1
        conc = g.groupby("ticker")["pnl"].sum()
        pos = conc[conc > 0].sum()
        top = conc.max() / pos * 100 if pos > 0 else np.nan
        winpos = (ws["ret"] > 0).mean() * 100
        checks = [pooled >= 0.0010, winpos >= 60, ws["dd"].min() >= -0.20, top <= 40]
        p(f"{name:10s} {len(g):6,} {pooled*100:+8.3f}% {winr:4.0f}% {slr:3.0f}% "
          f"{winpos:7.0f}% {eqs*100:+9.2f}% {ws['dd'].min()*100:7.1f}% {top:6.0f}%  "
          f"{'pass' if all(checks) else 'fail'} ({sum(checks)}/4)")
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/holds_stops_backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
