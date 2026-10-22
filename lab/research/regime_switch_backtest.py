#!/usr/bin/env python3
"""Regime-switched pump trader — full-span 2023-01 -> 2026-10.

Thesis (from oos_backtest findings): the pump event is the signal; the regime
decides the direction. 2023-24 pumps resolved by continuation (longs paid),
2025-26 by exhaustion (shorts paid). This tests whether a CAUSAL dial — the
trailing mean 24h forward return of already-completed pump events — can pick
the direction live, with no knowledge of the future.

Dial, at any time T:
  pump events = any alive bar with runup >= 12%/4h (no weakness/vol filter,
  broader sample), per-ticker 24h cooldown. An event's outcome (fwd 24h close
  return) is usable only once T >= event_time + 24h.
  m = mean fwd return of completed events in the trailing WINDOW days.
  m < -THR -> exhaustion regime -> SHORT the trade signal
  m > +THR -> continuation regime -> LONG the trade signal
  else (or < MIN_EV events) -> stand aside.

Trade signal = the frozen base rule (runup>=12%/4h, first red close, vol>=2x).
Short: stop at 4h high, 16c hold (the pre-registered rule, unchanged).
Long:  exact mirror — stop at 4h low, 16c hold.
Fees/sizing/kill-switch identical to rules_backtest.py.

Honesty note: the dial's WINDOW/THR are being chosen NOW, after seeing both
regimes. A small grid is reported (sensitivity, not cherry-pick); any live use
needs its own pre-registration. Arms reported per quarter:
  short-only (current fleet), long-only, switched, and the dial state itself.

Usage: python3 regime_switch_backtest.py
Writes: reports/regime_switch_<stamp>.txt, backtest/trades_regime.csv.gz
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import regime
# Canonical dial machinery lives in regime.py; re-exported here because the
# research scripts historically import it from this module.
from core.regime import alive, make_dial                        # noqa: F401
from wf_engine import ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, KILL_DD, \
    KILL_LOOKBACK, KILL_PAUSE
from backtest import M15
from rules_backtest import TAKER, SLIP

DAY = regime.DAY
FWD = regime.FWD_BARS_15M     # 24h in 15m bars — the event-outcome horizon
COOLDOWN = regime.FWD_BARS_15M   # per-ticker event dedup
GRID = [(30, 0.0), (60, 0.0), (90, 0.0), (60, 0.005), (60, 0.01)]
MAIN = (60, 0.0)    # the arm reported per-quarter
MIN_EV = regime.MIN_EV
pump_events = regime.pump_events_15m

WINDOWS = []
for y in (2023, 2024, 2025, 2026):
    for q, (a, b) in enumerate([("01-01", "04-01"), ("04-01", "07-01"),
                                ("07-01", "10-01"), ("10-01", "12-31")], 1):
        lo, hi = f"{y}-{a}", (f"{y + 1}-01-01" if q == 4 else f"{y}-{b}")
        if lo < "2026-10-01":
            WINDOWS.append((f"{y}Q{q}", lo, min(hi, "2026-10-03")))

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def load_full():
    """Both caches concatenated: continuous 2023-01 -> 2026-10 per ticker."""
    c15 = pd.concat([pd.read_csv("backtest/r60_oos_15m.csv.gz"),
                     pd.read_csv("backtest/r60_candles_15m.csv.gz")])
    tickers = {}
    for tk, g in c15.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if len(g) < 500:
            continue
        tickers[tk] = dict(t=g["t"].to_numpy(np.int64),
                           o=g["o"].to_numpy(float), h=g["h"].to_numpy(float),
                           l=g["l"].to_numpy(float), c=g["c"].to_numpy(float),
                           v=g["v"].to_numpy(float))
    return tickers


def signals(d, t0, t1):
    """Frozen base trigger: runup>=12%/4h, red close, vol>=2x."""
    t, c, v = d["t"], d["c"], d["v"]
    lo, hi = np.searchsorted(t, t0 - M15), np.searchsorted(t, t1 - M15)
    out = []
    for i in range(max(lo, 20), hi):
        if not alive(d, i):
            continue
        if c[i] / c[i - 16] - 1 < 0.12 or c[i] >= c[i - 1]:
            continue
        mu = v[i - 8:i].mean()
        if mu <= 0 or v[i] / mu < 2.0:
            continue
        out.append((t[i] + M15, i))
    return out


def exit_trade(d, i, entry, side):
    """side=-1 short (stop 4h high), side=+1 long (mirror, stop 4h low)."""
    if side < 0:
        level = d["h"][i - 16:i + 1].max()
    else:
        level = d["l"][i - 16:i + 1].min()
    init_dist = abs(level / entry - 1)
    for j in range(i + 1, min(i + 17, len(d["t"]))):
        hit = d["h"][j] > level if side < 0 else d["l"][j] < level
        if hit:
            gross = side * (level / entry - 1)
            return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", init_dist
    j = min(i + 16, len(d["t"]) - 1)
    gross = side * (d["c"][j] / entry - 1)
    return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "time", init_dist


def portfolio(sig_rows, tickers, side_fn):
    """side_fn(t_sig) -> -1/0/+1. Same risk model as the fleet."""
    trades, pending, open_until = [], [], {}
    equity, eq_hist, kill_until = 1.0, [], 0
    n_skip = 0
    for t_sig, tk, i in sorted(sig_rows):
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            equity += pnl
            eq_hist.append((et, equity))
        side = side_fn(t_sig)
        if side == 0:
            n_skip += 1
            continue
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
        net, exit_t, kind, sl_dist = exit_trade(d, i, entry, side)
        notional = min(RISK * equity / max(sl_dist, 0.005), NOTIONAL_CAP * equity)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades.append(dict(ticker=tk, t=t_sig, side=side, kind=kind,
                           net=net, pnl=pnl))
    for et, pnl in sorted(pending):
        equity += pnl
        eq_hist.append((et, equity))
    return trades, eq_hist, n_skip


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"REGIME-SWITCHED PUMP TRADER — {stamp} | full span 2023-01 -> 2026-10")
    p("dial = trailing mean 24h fwd return of completed pump events (causal)")
    p("")
    tickers = load_full()
    p(f"universe: {len(tickers)} tickers with continuous data")

    ev_t, ev_r, ev_done = pump_events(tickers)
    p(f"pump events (runup>=12%/4h, 24h cooldown): {len(ev_t):,} "
      f"from {pd.to_datetime(ev_t[0], unit='ms').date()} "
      f"to {pd.to_datetime(ev_t[-1], unit='ms').date()}")

    # --- dial state over time (monthly snapshot, main setting) ---
    wdays, thr = MAIN
    dial = make_dial(ev_t, ev_r, ev_done, wdays, thr)
    p("")
    p(f"DIAL STATE BY MONTH (window={wdays}d thr={thr:.1%}) "
      "[-1 short / 0 flat / +1 long], n events, mean fwd 24h")
    cur = ts("2023-03-01")
    end = ts("2026-10-01")
    while cur < end:
        s, n, m = dial(cur)
        tag = {-1: "SHORT", 0: "flat ", 1: "LONG "}[s]
        p(f"  {pd.to_datetime(cur, unit='ms').strftime('%Y-%m')}: {tag} "
          f"(n={n:3d}, m={m*100 if m == m else float('nan'):+.2f}%)")
        cur = (pd.to_datetime(cur, unit="ms") + pd.DateOffset(months=1)).value // 10**6

    # --- collect signals once ---
    sig_by_win = {}
    for wname, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i) for tsg, i in signals(d, t0, t1)]
        sig_by_win[wname] = (rows, t0, t1)

    arms = {
        "short-only": lambda T: -1,
        "long-only": lambda T: 1,
        "switched": lambda T: dial(T)[0],
    }
    p("")
    p("PER-QUARTER — same signal, three direction policies")
    p(f"{'win':7s} {'arm':11s} {'trades':>6s} {'skip':>5s} {'net/trade':>10s} "
      f"{'win%':>5s} {'eq':>8s} {'dd':>7s}")
    store, win_stats = [], {k: [] for k in arms}
    for wname, a, b in WINDOWS:
        rows, t0, t1 = sig_by_win[wname]
        for arm, fn in arms.items():
            trades, eqh, nskip = portfolio(rows, tickers, fn)
            met = metrics(eqh, t0, t1)
            nets = [x["net"] for x in trades]
            wr = np.mean([x["net"] > 0 for x in trades]) * 100 if trades else 0
            p(f"{wname:7s} {arm:11s} {len(trades):6,} {nskip:5,} "
              f"{np.mean(nets)*100 if nets else 0:+9.3f}% {wr:4.0f}% "
              f"{met['ret']*100:+7.2f}% {met['maxdd']*100:6.2f}%")
            for x in trades:
                x.update(window=wname, arm=arm)
            store += trades
            win_stats[arm].append(dict(window=wname, n=len(trades),
                                       net=np.mean(nets) if nets else np.nan,
                                       ret=met["ret"], dd=met["maxdd"]))

    t = pd.DataFrame(store)
    t.to_csv("backtest/trades_regime.csv.gz", index=False, compression="gzip")

    p("")
    p("=" * 100)
    p("FULL-SPAN SUMMARY 2023-01 -> 2026-10")
    p(f"{'arm':11s} {'trades':>6s} {'net/trade':>10s} {'win%':>5s} "
      f"{'windows+':>8s} {'compounded':>10s} {'worst dd':>8s}")
    for arm in arms:
        g = t[t["arm"] == arm]
        ws = pd.DataFrame(win_stats[arm])
        traded = ws[ws["n"] > 0]
        comp = (1 + ws["ret"]).prod() - 1
        winp = (traded["ret"] > 0).mean() * 100 if len(traded) else np.nan
        p(f"{arm:11s} {len(g):6,} {g['net'].mean()*100:+9.3f}% "
          f"{(g['net'] > 0).mean()*100:4.0f}% {winp:7.0f}% "
          f"{comp*100:+9.2f}% {ws['dd'].min()*100:7.1f}%")

    # year x arm breakdown
    p("")
    p("BY YEAR x ARM (net/trade % | trades)")
    t["year"] = pd.to_datetime(t["t"], unit="ms").dt.year
    for arm in arms:
        g = t[t["arm"] == arm]
        parts = []
        for y in (2023, 2024, 2025, 2026):
            gy = g[g["year"] == y]
            parts.append(f"{y}: {gy['net'].mean()*100:+.2f}%/{len(gy):,}"
                         if len(gy) else f"{y}: --")
        p(f"  {arm:11s} " + " | ".join(parts))

    # dial grid sensitivity (switched arm only, full span pooled)
    p("")
    p("DIAL GRID SENSITIVITY (switched arm, pooled full span)")
    p(f"{'window':>7s} {'thr':>6s} {'trades':>6s} {'net/trade':>10s} "
      f"{'compounded':>10s} {'worst dd':>8s}")
    for wd, th in GRID:
        dl = make_dial(ev_t, ev_r, ev_done, wd, th)
        fn = lambda T: dl(T)[0]
        comp_parts, nets_all, dds = [], [], []
        ntr = 0
        for wname, a, b in WINDOWS:
            rows, t0, t1 = sig_by_win[wname]
            trades, eqh, _ = portfolio(rows, tickers, fn)
            met = metrics(eqh, t0, t1)
            comp_parts.append(met["ret"])
            dds.append(met["maxdd"])
            nets_all += [x["net"] for x in trades]
            ntr += len(trades)
        comp = float(np.prod([1 + r for r in comp_parts]) - 1)
        p(f"{wd:6d}d {th:5.1%} {ntr:6,} "
          f"{np.mean(nets_all)*100 if nets_all else 0:+9.3f}% "
          f"{comp*100:+9.2f}% {min(dds)*100:7.1f}%")

    p("")
    p("CAVEATS: dial window/threshold chosen in 2026 with both regimes known —")
    p("the grid above is the honesty check. Long arm is a mirror, never")
    p("pre-registered. 2023-24 universe is survivor-thin (47 tickers, majors-")
    p("heavy). Any live use requires pre-registration round two.")

    os.makedirs("reports", exist_ok=True)
    fname = f"reports/regime_switch_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
