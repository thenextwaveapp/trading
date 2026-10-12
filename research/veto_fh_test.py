#!/usr/bin/env python3
"""VETO_FH TEST — does base + regime veto + failed-high confirm earn a slot?

Arms (same data, same costs, same engine):
  base     — enter at signal close
  veto     — base, but SKIP if dial > +2% at entry (causal dial; no veto when
             dial unknown). NOT gate30: veto only blocks hostile, gate
             requires friendly.
  fh       — enter at close of NEXT 15m bar only if its high < signal bar
             high; else skip entirely
  veto_fh  — both

Costs: 0.14% round trip (2x taker 0.045 + slip 0.05), PLUS 0.3% extra
slippage on stop exits. Same for every arm.
Dial: trailing 30d mean 24h-fwd return of pump events, completed events only
(make_dial is causal by construction).

Periods: IS 2023-01..2024-12 (oos cache, don't tune) | OOS 2025-01..today
(r60 cache — the verdict) | 2024 alone (pumps ran) | 2026 alone (pumps fade).

Slot criteria (OOS): avg net > base, worst dd <= base's, >=50 trades,
dropped trades averaged worse than kept.

Usage: python3 research/veto_fh_test.py
Writes: reports/veto_fh_test_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np

from rules_backtest import load
from degen_derby import precompute, sig_pump
from regime_switch_backtest import pump_events, make_dial
from backtest import M15

COST_RT = 0.0014          # round trip: 2x taker + slip (current fleet model)
SLIP_STOP = 0.003         # extra slippage when the exit is a stop
RISK, NOTIONAL_CAP, MAX_CONC = 0.0075, 0.20, 6
VETO_THR = 0.02

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def resolve_trade(d, sig_i, entry_bar):
    """Short from close[entry_bar]; stop = signal-window 4h high; hold 16
    bars from entry. Returns (net, exit_t, kind, sl_dist)."""
    t, h, c = d["t"], d["h"], d["c"]
    entry = c[entry_bar]
    sl = h[max(sig_i - 16, 0):sig_i + 1].max()
    end = min(entry_bar + 16, len(t) - 1)
    for j in range(entry_bar + 1, end + 1):
        if h[j] > sl:
            return (-(sl / entry - 1) - COST_RT - SLIP_STOP,
                    t[j] + M15, "sl", sl / entry - 1)
    return (-(c[end] / entry - 1) - COST_RT,
            t[end] + M15, "time", sl / entry - 1)


def gen_rows(tickers, t0, t1, confirm_fh):
    """(entry_t, tk, sig_i, entry_bar) for all base signals in [t0,t1);
    confirm_fh also returns the skip list (failed confirmation)."""
    rows, dropped = [], []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        t, h = d["t"], d["h"]
        for i in ii:
            t_sig = t[i] + M15
            if not (t0 <= t_sig < t1):
                continue
            if not confirm_fh:
                rows.append((t_sig, tk, i, i))
                continue
            if i + 1 >= len(t) or t[i + 1] - t[i] != M15:
                dropped.append((tk, i))
                continue
            if h[i + 1] < h[i]:
                rows.append((t[i + 1] + M15, tk, i, i + 1))
            else:
                dropped.append((tk, i))
    rows.sort()
    return rows, dropped


def run_arm(tickers, dial, t0, t1, veto=False, fh=False):
    rows, fh_dropped = gen_rows(tickers, t0, t1, fh)
    eq, peak, maxdd = 1.0, 1.0, 0.0
    pending, open_until = [], {}
    nets, veto_dropped = [], []
    for entry_t, tk, sig_i, entry_bar in rows:
        pending.sort()
        while pending and pending[0][0] <= entry_t:
            _, pnl = pending.pop(0)
            eq += pnl
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if open_until.get(tk, 0) > entry_t:
            continue
        if sum(1 for x in open_until.values() if x > entry_t) >= MAX_CONC:
            continue
        if veto:
            s, n, m = dial(entry_t)
            if m == m and m is not None and m > VETO_THR:
                veto_dropped.append((tk, sig_i))
                continue
        d = tickers[tk]
        net, exit_t, kind, sl_dist = resolve_trade(d, sig_i, entry_bar)
        notional = min(RISK * eq / max(abs(sl_dist), 0.005), NOTIONAL_CAP * eq)
        pending.append((exit_t, notional * net))
        open_until[tk] = exit_t
        nets.append(net)
    for _, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    nets = np.array(nets) if nets else np.array([])
    return dict(n=len(nets), avg=nets.mean() if len(nets) else np.nan,
                win=(nets > 0).mean() if len(nets) else np.nan,
                ret=eq - 1, maxdd=maxdd,
                dropped=veto_dropped + fh_dropped)


def base_outcome(tickers, drops):
    """What the dropped signals would have done traded base-style."""
    nets = [resolve_trade(tickers[tk], i, i)[0] for tk, i in drops]
    return (np.mean(nets), len(nets)) if nets else (np.nan, 0)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"VETO_FH TEST — {stamp}")
    p(f"costs: {COST_RT*100:.2f}% RT + {SLIP_STOP*100:.1f}% extra on stop exits | "
      f"sizing {RISK*100:.2f}% risk cap {NOTIONAL_CAP*100:.0f}% conc {MAX_CONC} | veto thr +{VETO_THR*100:.0f}%")
    p("")

    caches = {}
    for key, c15, c1 in [("is", "backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
                         ("oos", "backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")]:
        tickers, _ = load(c15, c1)
        for d in tickers.values():
            precompute(d)
        dial = make_dial(*pump_events(tickers), 30, 0.0)
        caches[key] = (tickers, dial)
        p(f"loaded {key}: {len(tickers)} tickers")
    p("")

    def ts(iso):
        return int(datetime.fromisoformat(iso + "T00:00:00+00:00").timestamp() * 1000)

    periods = [
        ("IS 2023-01..2024-12", "is", ts("2023-01-01"), ts("2025-01-01")),
        ("2024 alone", "is", ts("2024-01-01"), ts("2025-01-01")),
        ("OOS 2025-01..today  *VERDICT*", "oos", ts("2025-01-01"), ts("2026-12-31")),
        ("2026 alone", "oos", ts("2026-01-01"), ts("2026-12-31")),
    ]
    ARMS = [("base", False, False), ("veto", True, False),
            ("fh", False, True), ("veto_fh", True, True)]

    oos_res = {}
    for plabel, ckey, t0, t1 in periods:
        tickers, dial = caches[ckey]
        p("=" * 96)
        p(plabel)
        p(f"  {'arm':8s} {'trades':>6s} {'avg net':>9s} {'win':>6s} {'eq ret':>9s} "
          f"{'maxdd':>7s} {'dropped':>8s} {'drop avg(base)':>15s}")
        base_r = None
        for name, veto, fh in ARMS:
            r = run_arm(tickers, dial, t0, t1, veto, fh)
            if name == "base":
                base_r = r
            davg, dn = base_outcome(tickers, r["dropped"])
            p(f"  {name:8s} {r['n']:6d} {r['avg']*100:+8.3f}% {r['win']*100:5.1f}% "
              f"{r['ret']*100:+8.2f}% {r['maxdd']*100:6.1f}% {dn:8d} "
              f"{'' if dn == 0 else f'{davg*100:+9.3f}%':>15s}")
            if plabel.startswith("OOS"):
                oos_res[name] = dict(r, drop_avg=davg, drop_n=dn)
        p("")

    p("=" * 96)
    p("SLOT CRITERIA (OOS 2025-01..today):")
    b = oos_res["base"]
    for name in ("veto", "fh", "veto_fh"):
        r = oos_res[name]
        kept_avg = r["avg"]
        checks = [
            ("avg net > base", r["avg"] > b["avg"]),
            ("maxdd no worse than base", r["maxdd"] >= b["maxdd"]),
            (">= 50 trades", r["n"] >= 50),
            ("dropped avg worse than kept",
             r["drop_n"] > 0 and r["drop_avg"] < kept_avg),
        ]
        verdict = "PASS" if all(ok for _, ok in checks) else "FAIL"
        p(f"  {name:8s} -> {verdict}  " +
          " | ".join(f"{lab}: {'Y' if ok else 'N'}" for lab, ok in checks))

    fname = f"reports/veto_fh_test_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh_:
        fh_.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
