#!/usr/bin/env python3
"""Dump-long (mirror rule) robustness battery.

Candidate from long_search.py: the exact structural mirror of the frozen
pump-short — 4h return <= -12%, FIRST GREEN CLOSE, vol >= 2x -> long at
15m close, stop = 4h low, 16-candle hold. Zero new parameters (all
inherited from the pre-registered short rule).

This script does NOT change the rule — it stress-tests around the frozen
point on the full span 2023-01 -> 2026-10 (quarterly windows):
  A. parameter sensitivity (one knob at a time)
  B. execution/cost stress + perishability delay ladder
  C. bootstrap CI on pooled net/trade
  D. leave-one-out (years, top tickers, top winners) + concentration
  E. random-LONG placebo matched per window (the beta control)
  F. BTC regime split
  G. episode clustering (independent dump episodes, not bar-level trades)

Usage: python3 long_robustness.py
Writes: reports/long_robustness_<stamp>.txt, backtest/dl_robustness_variants.csv
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, KILL_DD, \
    KILL_LOOKBACK, KILL_PAUSE
from backtest import M15, H
from regime_switch_backtest import load_full, WINDOWS
from long_search import precompute, COST, YEARS

DAY = 86_400_000

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- signals
def gen_signals(d, t0, t1, dump=0.12, volx=2.0, green=True):
    t = d["t"]
    lo = max(np.searchsorted(t, t0 - M15), 20)
    hi = np.searchsorted(t, t1 - M15)
    cond = d["alive_v"] & (d["ret4_v"] <= -dump) & (d["volr_v"] >= volx)
    if green:
        cond = cond & d["green_v"]
    cond[:lo] = False
    cond[hi:] = False
    return [(t[i] + M15, i) for i in np.nonzero(cond)[0]]


def make_exit(hold=16, stop_mode="base", cost_mult=1.0, delay=0,
              next_open=False):
    """delay k = enter at close of bar i+k (perishability probe).
    Sizing basis (sl_dist) fixed to the undelayed base stop across variants."""
    cost = COST * cost_mult

    def exit_fn(d, i):
        t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
        base_stop = l[i - 15:i + 1].min() * 0.999
        entry0 = c[i]
        sl_dist = abs(base_stop / entry0 - 1)
        if next_open:
            if i + 1 >= len(t):
                return None
            entry, start = o[i + 1], i + 1
        elif delay:
            if i + delay >= len(t):
                return None
            entry, start = c[i + delay], i + delay
        else:
            entry, start = entry0, i
        level = {"base": base_stop, "buf1": base_stop * 0.99,
                 "none": -np.inf}[stop_mode]
        for j in range(start + 1, min(start + hold + 1, len(t))):
            if l[j] < level:
                gross = level / entry - 1
                return gross - cost, t[j] + M15, "sl", sl_dist
        j = min(start + hold, len(t) - 1)
        return (c[j] / entry - 1) - cost, t[j] + M15, "time", sl_dist

    return exit_fn


def portfolio(sig_rows, tickers, exit_fn):
    trades, pending, open_until = [], [], {}
    equity, eq_hist, kill_until = 1.0, [], 0
    for t_sig, tk, i in sorted(sig_rows):
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
        res = exit_fn(tickers[tk], i)
        if res is None:
            continue
        net, exit_t, kind, sl_dist = res
        notional = min(RISK * equity / max(sl_dist, 0.005),
                       NOTIONAL_CAP * equity)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades.append(dict(ticker=tk, t=t_sig, kind=kind, net=net, pnl=pnl))
    for et, pnl in sorted(pending):
        equity += pnl
        eq_hist.append((et, equity))
    return trades, eq_hist


def run_variant(tickers, label, dump=0.12, volx=2.0, green=True,
                hold=16, stop_mode="base", cost_mult=1.0, delay=0,
                next_open=False):
    exit_fn = make_exit(hold, stop_mode, cost_mult, delay, next_open)
    all_trades, win_rows = [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i)
                     for tsg, i in gen_signals(d, t0, t1, dump, volx, green)]
        trades, eqh = portfolio(rows, tickers, exit_fn)
        met = metrics(eqh, t0, t1)
        for x in trades:
            x.update(window=name)
        all_trades += trades
        win_rows.append(dict(window=name, n=len(trades),
                             ret=met["ret"], dd=met["maxdd"]))
    tdf = pd.DataFrame(all_trades)
    ws = pd.DataFrame(win_rows)
    traded = ws[ws["n"] > 0]
    pooled = tdf["net"].mean() if len(tdf) else np.nan
    comp = (1 + ws["ret"]).prod() - 1
    summ = dict(variant=label, trades=len(tdf), pooled_net=pooled,
                median_net=tdf["net"].median() if len(tdf) else np.nan,
                win_rate=(tdf["net"] > 0).mean() if len(tdf) else np.nan,
                sl_rate=(tdf["kind"] == "sl").mean() if len(tdf) else np.nan,
                compounded=comp, worst_dd=ws["dd"].min(),
                winpos=(traded["ret"] > 0).mean() if len(traded) else np.nan,
                n_windows_traded=len(traded))
    p(f"{label:34s} trades {summ['trades']:4d} | net/trade "
      f"{pooled*100 if pooled == pooled else 0:+.3f}% | "
      f"med {summ['median_net']*100 if len(tdf) else 0:+.3f}% | "
      f"win {summ['win_rate']*100 if len(tdf) else 0:4.1f}% | "
      f"sl {summ['sl_rate']*100 if len(tdf) else 0:4.1f}% | "
      f"comp {comp*100:+.2f}% | dd {ws['dd'].min()*100:.2f}% | "
      f"wins+ {summ['winpos']*100 if len(traded) else 0:.0f}% "
      f"of {len(traded)}w")
    return summ, tdf


# ---------------------------------------------------------------- placebo
def placebo(tickers, counts_by_window, reps, rng):
    """Random-time LONGS, 16-candle hold, same costs, no stop — is the
    pooled edge just long-beta of these periods?"""
    tks = list(tickers)
    means = []
    for _ in range(reps):
        nets = []
        for name, a, b in WINDOWS:
            t0, t1 = ts(a), ts(b)
            need = counts_by_window.get(name, 0)
            got, tries = 0, 0
            while got < need and tries < need * 60:
                tries += 1
                d = tickers[tks[rng.integers(len(tks))]]
                lo = np.searchsorted(d["t"], t0)
                hi = np.searchsorted(d["t"], t1) - 17
                if hi <= max(lo, 20):
                    continue
                i = int(rng.integers(max(lo, 20), hi))
                if not d["alive_v"][i]:
                    continue
                nets.append((d["c"][i + 16] / d["c"][i] - 1) - COST)
                got += 1
        if nets:
            means.append(np.mean(nets))
    return np.array(means)


def btc_regime(tickers):
    """-> fn(T) True when BTC bull (4h EMA20 > EMA50)."""
    c1 = pd.concat([pd.read_csv("backtest/r60_oos_1h.csv.gz"),
                    pd.read_csv("backtest/r60_candles_1h.csv.gz")])
    b = c1[c1["ticker"] == "BTC"].drop_duplicates("t").sort_values("t")
    b4 = b.set_index("t")["c"].groupby(lambda t: t - t % (4 * H)).last()
    e20 = b4.ewm(span=20, adjust=False).mean().to_numpy()
    e50 = b4.ewm(span=50, adjust=False).mean().to_numpy()
    t4 = b4.index.to_numpy() + 4 * H

    def bull(T):
        j = np.searchsorted(t4, T, "right") - 1
        return bool(j >= 0 and e20[j] > e50[j])
    return bull


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    p(f"DUMP-LONG ROBUSTNESS BATTERY — {stamp} | {len(tickers)} tickers | "
      "full span 2023-01 -> 2026-10")
    p("frozen candidate = dump<=-12%/4h, first GREEN close, vol>=2x, LONG, "
      "stop=4h-low, hold=16c (exact mirror of pre-registered short)")
    p("")

    p("-" * 78)
    p("A. PARAMETER SENSITIVITY (one knob at a time from mirror point)")
    variants = [
        ("BASELINE (mirror rule)", {}),
        ("dump <= -8%", dict(dump=0.08)),
        ("dump <= -10%", dict(dump=0.10)),
        ("dump <= -14%", dict(dump=0.14)),
        ("dump <= -16%", dict(dump=0.16)),
        ("dump <= -20%", dict(dump=0.20)),
        ("vol >= 1.5x", dict(volx=1.5)),
        ("vol >= 2.5x", dict(volx=2.5)),
        ("vol >= 3x", dict(volx=3.0)),
        ("vol >= 4x", dict(volx=4.0)),
        ("no green filter", dict(green=False)),
        ("hold 8c (2h)", dict(hold=8)),
        ("hold 24c (6h)", dict(hold=24)),
        ("hold 32c (8h)", dict(hold=32)),
        ("hold 96c (24h)", dict(hold=96)),
        ("stop -1% buffer", dict(stop_mode="buf1")),
        ("no stop (time exit only)", dict(stop_mode="none")),
    ]
    summs, base_trades = [], None
    for label, kw in variants:
        s, tdf = run_variant(tickers, label, **kw)
        summs.append(s)
        if label.startswith("BASELINE"):
            base_trades = tdf

    p("")
    p("-" * 78)
    p("B. EXECUTION / COST STRESS + PERISHABILITY LADDER")
    for label, kw in [
        ("costs x1.5", dict(cost_mult=1.5)),
        ("costs x2", dict(cost_mult=2.0)),
        ("costs x3", dict(cost_mult=3.0)),
        ("costs x4", dict(cost_mult=4.0)),
        ("entry at next open (+0-15m)", dict(next_open=True)),
        ("entry +1 bar (15m late)", dict(delay=1)),
        ("entry +2 bars (30m late)", dict(delay=2)),
        ("entry +4 bars (1h late)", dict(delay=4)),
        ("entry +16 bars (4h late)", dict(delay=16)),
        ("next open + costs x2", dict(next_open=True, cost_mult=2.0)),
    ]:
        s, _ = run_variant(tickers, label, **kw)
        summs.append(s)

    pd.DataFrame(summs).to_csv("backtest/dl_robustness_variants.csv",
                               index=False)

    bt = base_trades.copy()
    nets = bt["net"].to_numpy()
    rng = np.random.default_rng(7)

    p("")
    p("-" * 78)
    p("C. BOOTSTRAP CI ON BASELINE (10,000 resamples of net/trade)")
    bs = np.array([rng.choice(nets, len(nets)).mean() for _ in range(10_000)])
    p(f"pooled net/trade {nets.mean()*100:+.3f}% | 95% CI "
      f"[{np.percentile(bs,2.5)*100:+.3f}%, {np.percentile(bs,97.5)*100:+.3f}%]"
      f" | P(mean<=0) = {(bs <= 0).mean()*100:.2f}%")

    p("")
    p("D. LEAVE-ONE-OUT + CONCENTRATION (baseline)")
    bt["year"] = pd.to_datetime(bt["t"], unit="ms").dt.year
    for y in YEARS:
        sub = bt[bt["year"] != y]["net"]
        iny = bt[bt["year"] == y]["net"]
        p(f"  drop {y}: {len(sub):3d} trades, net/trade {sub.mean()*100:+.3f}% "
          f"(year alone: {iny.mean()*100 if len(iny) else 0:+.3f}%/{len(iny)})")
    for tk in bt.groupby("ticker")["pnl"].sum().abs() \
                .sort_values(ascending=False).head(5).index:
        sub = bt[bt["ticker"] != tk]["net"]
        p(f"  drop {tk:10s}: {len(sub):3d} trades, net/trade "
          f"{sub.mean()*100:+.3f}%")
    srt = np.sort(nets)
    p(f"  drop top-5 winners : net/trade {srt[:-5].mean()*100:+.3f}%")
    p(f"  drop top-10 winners: net/trade {srt[:-10].mean()*100:+.3f}%")
    p(f"  max single loss {srt[0]*100:+.2f}% | max single win "
      f"{srt[-1]*100:+.2f}%")

    p("")
    p("E. RANDOM-LONG PLACEBO (matched counts/window, 200 reps)")
    counts = bt.groupby("window").size().to_dict()
    pl = placebo(tickers, counts, 200, rng)
    pct = (pl < nets.mean()).mean() * 100
    p(f"placebo net/trade: mean {pl.mean()*100:+.3f}%, 95th pct "
      f"{np.percentile(pl,95)*100:+.3f}% | actual {nets.mean()*100:+.3f}% "
      f"beats {pct:.1f}% of placebo runs")

    p("")
    p("F. REGIME SPLIT (BTC 4h EMA20 vs EMA50 at signal time, baseline)")
    bull = btc_regime(tickers)
    bt["bull"] = [bull(t) for t in bt["t"]]
    for lab, sub in bt.groupby("bull"):
        p(f"  {'bull' if lab else 'bear'}: {len(sub):3d} trades, net/trade "
          f"{sub['net'].mean()*100:+.3f}%, win "
          f"{(sub['net']>0).mean()*100:.0f}%")

    p("")
    p("G. EPISODE CLUSTERING (same ticker, trades < 24h apart = one episode)")
    bt = bt.sort_values(["ticker", "t"])
    ep, last_tk, last_t, eid = [], None, 0, 0
    for _, r in bt.iterrows():
        if r["ticker"] != last_tk or r["t"] - last_t > DAY:
            eid += 1
        ep.append(eid)
        last_tk, last_t = r["ticker"], r["t"]
    bt["ep"] = ep
    g = bt.groupby("ep").agg(net=("net", "mean"), n=("net", "size"),
                             pnl=("pnl", "sum"))
    p(f"  {len(bt)} trades -> {len(g)} independent episodes "
      f"(max {g['n'].max()} trades/episode)")
    p(f"  per-episode mean net {g['net'].mean()*100:+.3f}% | episodes "
      f"positive {(g['net']>0).mean()*100:.0f}% | top episode = "
      f"{g['pnl'].abs().max()/abs(g['pnl']).sum()*100:.0f}% of gross |pnl|")

    os.makedirs("reports", exist_ok=True)
    fname = ("reports/long_robustness_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
