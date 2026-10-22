#!/usr/bin/env python3
"""EXITS LAB — could Leverage Larry have made more?

Same 163 base-rule signals, same entry, same initial stop (4h high),
same sizing (25% margin at 4x, max 4 concurrent). Only the EXIT changes.

First: MFE autopsy — how deep did each collapse actually go within
4h/8h/24h/48h, and how much did the 4h time exit capture?
Then: race the exit policies at Larry sizing.

Usage: python3 exits_lab.py
Writes: reports/exits_lab_<stamp>.txt
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load
from degen_derby import precompute, sig_pump, COST, START
from backtest import M15

FRAC, LEV, CONC = 0.25, 4, 4         # Larry's rig
LIQ = 1.0 / LEV - 0.005              # adverse move that wipes margin

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


# ------------------------------------------------------------ path walker
def walk(d, i, policy):
    """Short entry at c[i]. Initial stop = signal 4h high, always active.
    Returns (net, exit_t, kind). policy decides the exit beyond the stop."""
    t, h, l, c = d["t"], d["h"], d["l"], d["c"]
    entry = c[i]
    n = len(t)
    sl = h[max(i - 16, 0):i + 1].max()
    liq_price = entry * (1 + LIQ)
    mode, arg = policy

    if mode == "time":
        hold = arg
    elif mode == "tp":
        hold = arg[1]
    elif mode == "be":
        hold = 96
    else:
        hold = 192
    end = min(i + hold, n - 1)

    min_close = entry
    be_armed = False
    runner_phase = False
    tp_price = entry * (1 - arg[0]) if mode == "tp" else None
    trail_pct = arg if mode == "trail" else (0.03 if mode in ("runner", "half") else None)

    for j in range(i + 1, end + 1):
        # liquidation first, then stop
        if h[j] >= liq_price:
            return -LIQ - COST, t[j] + M15, "LIQ"
        stop_now = entry if (mode == "be" and be_armed) else sl
        if mode in ("trail", "runner", "half") and min_close < entry:
            # trailing: stop ratchets down to trail_pct above the running min close
            stop_now = min(stop_now, min_close * (1 + trail_pct)) if (mode != "runner" or runner_phase) else stop_now
        if h[j] > stop_now:
            return -(stop_now / entry - 1) - COST, t[j] + M15, "sl" if stop_now == sl else "trail"
        if mode == "tp" and l[j] <= tp_price:
            return -(tp_price / entry - 1) - COST, t[j] + M15, "tp"
        min_close = min(min_close, c[j])
        if mode == "be" and c[j] <= entry * 0.98:
            be_armed = True
        if mode == "green" and j >= i + 4 and c[j] > c[j - 1]:
            return -(c[j] / entry - 1) - COST, t[j] + M15, "green"
        if mode == "runner" and j == i + 16:
            pnl_4h = -(c[j] / entry - 1)
            if pnl_4h < 0.05:
                return pnl_4h - COST, t[j] + M15, "time"
            runner_phase = True
        if mode == "time" and j == i + arg:
            return -(c[j] / entry - 1) - COST, t[j] + M15, "time"
        if mode == "half" and j == i + 16:
            # book half at 4h, let half trail — approximate as blended net
            first_half = -(c[j] / entry - 1)
            net2, et2, k2 = walk_trail_from(d, i, j, entry, sl, liq_price, trail_pct, end)
            return 0.5 * first_half + 0.5 * net2 - COST, et2, "half"
    j = end
    return -(c[j] / entry - 1) - COST, t[j] + M15, "time"


def walk_trail_from(d, i, start_j, entry, sl, liq_price, trail_pct, end):
    t, h, c = d["t"], d["h"], d["c"]
    min_close = min(entry, c[i + 1:start_j + 1].min())
    for j in range(start_j + 1, end + 1):
        if h[j] >= liq_price:
            return -LIQ, t[j] + M15, "LIQ"
        stop_now = min(sl, min_close * (1 + trail_pct)) if min_close < entry else sl
        if h[j] > stop_now:
            return -(stop_now / entry - 1), t[j] + M15, "trail"
        min_close = min(min_close, c[j])
    return -(c[end] / entry - 1), t[end] + M15, "time"


# ------------------------------------------------------------ race engine
def race_policy(label, sigs, tickers, policy):
    equity, peak, maxdd = START, START, 0.0
    pending, open_until = [], {}
    trades = wins = liqs = 0
    nets = []
    for t_sig, tk, i in sigs:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl, won, lq = pending.pop(0)
            equity += pnl
            wins += won
            liqs += lq
            peak = max(peak, equity)
            maxdd = min(maxdd, equity / peak - 1)
        if equity < START * 0.01:
            break
        if open_until.get(tk, 0) > t_sig:
            continue
        if sum(1 for x in open_until.values() if x > t_sig) >= CONC:
            continue
        d = tickers[tk]
        net, exit_t, kind = walk(d, i, policy)
        margin = min(FRAC * equity, equity)
        pnl = max(margin * LEV * net, -margin)
        pending.append((exit_t, pnl, net > 0, kind == "LIQ"))
        open_until[tk] = exit_t
        trades += 1
        nets.append(net)
    for et, pnl, won, lq in sorted(pending):
        equity += pnl
        wins += won
        liqs += lq
        peak = max(peak, equity)
        maxdd = min(maxdd, equity / peak - 1)
    equity = max(equity, 0.0)
    nets = np.array(nets) if nets else np.array([0.0])
    return dict(label=label, final=equity, trades=trades,
                avg=nets.mean(), med=np.median(nets),
                win=(nets > 0).mean(), maxdd=maxdd, liqs=liqs)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, _ = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    sigs = []
    for tk, d in tickers.items():
        ii, _ = sig_pump(d)
        sigs += [(d["t"][i] + M15, tk, i) for i in ii]
    sigs.sort()

    p(f"EXITS LAB — {stamp} | same signals, same entry, same 4h-high stop,")
    p(f"same Larry sizing (25% margin at {LEV}x, max {CONC} concurrent) — only the exit changes")
    p("")

    # ---------------- MFE autopsy
    p("MFE AUTOPSY (per-ticker-lock trades, no concurrency cap — how deep do collapses go?)")
    open_until, rows = {}, []
    for t_sig, tk, i in sigs:
        if open_until.get(tk, 0) > t_sig:
            continue
        d = tickers[tk]
        t, c, l = d["t"], d["c"], d["l"]
        entry = c[i]
        n = len(t)
        sl = d["h"][max(i - 16, 0):i + 1].max()
        stopped = None
        for j in range(i + 1, min(i + 17, n)):
            if d["h"][j] > sl:
                stopped = j
                break
        row = dict(entry=entry)
        for nm, bars in [("4h", 16), ("8h", 32), ("24h", 96), ("48h", 192)]:
            e = min(i + bars, n - 1)
            row[f"mfe{nm}"] = -(l[i + 1:e + 1].min() / entry - 1) if e > i else 0.0
        e16 = min(i + 16, n - 1)
        row["realized"] = -(sl / entry - 1) - COST if stopped else -(c[e16] / entry - 1) - COST
        row["stopped"] = stopped is not None
        open_until[tk] = t[min(i + 16, n - 1)] + M15
        rows.append(row)
    a = pd.DataFrame(rows)
    surv = a[~a.stopped]
    p(f"  all {len(a)} trades: deepest collapse (low) within 4h avg {a.mfe4h.mean()*100:.1f}% | "
      f"8h {a.mfe8h.mean()*100:.1f}% | 24h {a.mfe24h.mean()*100:.1f}% | 48h {a.mfe48h.mean()*100:.1f}%")
    p(f"  survivors (n={len(surv)}): 4h {surv.mfe4h.mean()*100:.1f}% | 8h {surv.mfe8h.mean()*100:.1f}% | "
      f"24h {surv.mfe24h.mean()*100:.1f}% | 48h {surv.mfe48h.mean()*100:.1f}%")
    p(f"  4h time exit realizes {a.realized.mean()*100:+.2f}%/trade = "
      f"{a.realized.mean()/max(a.mfe24h.mean(),1e-9)*100:.0f}% of the avg 24h max collapse")
    p("")

    # ---------------- exit policy race
    policies = [
        ("CONTROL: time exit 4h (Larry as raced)", ("time", 16)),
        ("time exit 2h", ("time", 8)),
        ("time exit 8h", ("time", 32)),
        ("time exit 24h", ("time", 96)),
        ("time exit 48h", ("time", 192)),
        ("first green candle (after 1h)", ("green", None)),
        ("trail 2% off min close, up to 48h", ("trail", 0.02)),
        ("trail 3% off min close, up to 48h", ("trail", 0.03)),
        ("trail 5% off min close, up to 48h", ("trail", 0.05)),
        ("breakeven stop once -2%, hold 24h", ("be", None)),
        ("take-profit -10% or 24h", ("tp", (0.10, 96))),
        ("take-profit -20% or 24h", ("tp", (0.20, 96))),
        ("runner: exit 4h unless >+5%, then trail 3%", ("runner", None)),
        ("half at 4h + half trails 3% to 48h", ("half", None)),
    ]
    p("EXIT POLICY RACE (final $ at Larry sizing):")
    res = [race_policy(lab, sigs, tickers, pol) for lab, pol in policies]
    res.sort(key=lambda r: r["final"], reverse=True)
    for k, r in enumerate(res):
        tag = f" ⚡{r['liqs']}liq" if r["liqs"] else ""
        p(f"  {k+1:2d}. {r['label']:44s} ${r['final']:>12,.0f}  avg {r['avg']*100:+6.2f}%  "
          f"med {r['med']*100:+5.2f}%  win {r['win']*100:4.1f}%  dd {r['maxdd']*100:6.1f}%  "
          f"n={r['trades']}{tag}")

    fname = f"reports/exits_lab_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
