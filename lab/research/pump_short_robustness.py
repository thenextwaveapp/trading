#!/usr/bin/env python3
"""Pump-short (rule P) robustness battery.

The frozen rule passed its pre-registered gate (reports/rules_backtest_*.txt).
This script does NOT change the rule — it stress-tests the same signal around
the frozen point: parameter grids, cost stress, delayed fills, filter ablation,
leave-one-out, bootstrap CI, random-short placebo, regime split.

Usage: python3 pump_short_robustness.py
Writes: reports/pump_short_robustness_<stamp>.txt, backtest/ps_robustness_variants.csv
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rules_backtest import load, portfolio, TAKER, SLIP
from wf_engine import WINDOWS, ts, metrics
from backtest import M15

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


# ------------------------------------------------------------- vectorized P
def precompute(d):
    t, c, v, h, l = d["t"], d["c"], d["v"], d["h"], d["l"]
    n = len(t)
    gap_ok = np.zeros(n, bool)
    gap_ok[16:] = (t[16:] - t[:-16]) == 16 * M15
    vall = pd.Series(v > 0).rolling(9).min().to_numpy() == 1
    d["alive_v"] = gap_ok & vall & (h != l) & (np.arange(n) >= 20)
    ru = np.full(n, np.nan)
    ru[16:] = c[16:] / c[:-16] - 1
    d["runup_v"] = ru
    wk = np.zeros(n, bool)
    wk[1:] = c[1:] < c[:-1]
    d["weak_v"] = wk
    mu = pd.Series(v).rolling(8).mean().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        d["volr_v"] = np.where(mu > 0, v / mu, np.nan)


def gen_signals(d, t0, t1, runup_th, volx, need_weak):
    t = d["t"]
    lo = max(np.searchsorted(t, t0 - M15), 20)
    hi = np.searchsorted(t, t1 - M15)
    cond = d["alive_v"] & (d["runup_v"] >= runup_th) & (d["volr_v"] >= volx)
    if need_weak:
        cond = cond & d["weak_v"]
    cond[:lo] = False
    cond[hi:] = False
    ii = np.nonzero(cond)[0]
    return [(t[i] + M15, i, d["runup_v"][i]) for i in ii]


def make_exit(hold=16, stop="base", cost_mult=1.0, delay=False):
    cost = (2 * TAKER + SLIP) * cost_mult

    def exit_fn(d, i, entry):
        t, h, c, o = d["t"], d["h"], d["c"], d["o"]
        if delay and i + 1 < len(t):
            entry = o[i + 1]
        base_sl = h[i - 16:i + 1].max()
        sl_level = {"base": base_sl, "buf1": base_sl * 1.01, "none": np.inf}[stop]
        sl_dist = base_sl / entry - 1  # sizing basis fixed across variants
        for j in range(i + 1, min(i + hold + 1, len(t))):
            if h[j] > sl_level:
                return -(sl_level / entry - 1) - cost, t[j] + M15, "sl", sl_dist
        j = min(i + hold, len(t) - 1)
        return -(c[j] / entry - 1) - cost, t[j] + M15, "time", sl_dist

    return exit_fn


def run_variant(tickers, label, runup=0.12, volx=2.0, weak=True,
                hold=16, stop="base", cost_mult=1.0, delay=False):
    exit_fn = make_exit(hold, stop, cost_mult, delay)
    all_trades, win_rows = [], []
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        rows = []
        for tk, d in tickers.items():
            rows += [(tsg, tk, i, ru) for tsg, i, ru in gen_signals(d, t0, t1, runup, volx, weak)]
        trades, eqh = portfolio(rows, tickers, exit_fn)
        met = metrics(eqh, t0, t1)
        for x in trades:
            x.update(window=name)
        all_trades += trades
        win_rows.append(dict(window=name, n=len(trades),
                             net=np.mean([x["net"] for x in trades]) if trades else np.nan,
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
      f"{pooled*100 if pooled == pooled else 0:+.3f}% | med {summ['median_net']*100 if len(tdf) else 0:+.3f}% | "
      f"win {summ['win_rate']*100 if len(tdf) else 0:4.1f}% | sl {summ['sl_rate']*100 if len(tdf) else 0:4.1f}% | "
      f"comp {comp*100:+.2f}% | worst dd {ws['dd'].min()*100:.2f}% | "
      f"wins+ {summ['winpos']*100 if len(traded) else 0:.0f}% of {len(traded)}w")
    return summ, tdf


# ------------------------------------------------------------------ placebo
def placebo(tickers, counts_by_window, reps, rng):
    """Random-time SHORTS, 16-candle hold, same costs, no stop — is the pooled
    edge just short-bias of these periods?"""
    cost = 2 * TAKER + SLIP
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
                nets.append(-(d["c"][i + 16] / d["c"][i] - 1) - cost)
                got += 1
        if nets:
            means.append(np.mean(nets))
    return np.array(means)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    p(f"PUMP-SHORT ROBUSTNESS BATTERY — {stamp} | universe {len(tickers)} tickers | "
      f"frozen rule = runup>=12%/4h, weak close, vol>=2x, short, stop=4h-high, hold=16c")
    p("")

    p("-" * 78)
    p("A. PARAMETER SENSITIVITY (one knob at a time from frozen point)")
    variants = [
        ("BASELINE (frozen rule)", {}),
        ("runup >= 8%", dict(runup=0.08)),
        ("runup >= 10%", dict(runup=0.10)),
        ("runup >= 14%", dict(runup=0.14)),
        ("runup >= 16%", dict(runup=0.16)),
        ("runup >= 20%", dict(runup=0.20)),
        ("vol >= 1.5x", dict(volx=1.5)),
        ("vol >= 2.5x", dict(volx=2.5)),
        ("vol >= 3x", dict(volx=3.0)),
        ("vol >= 4x", dict(volx=4.0)),
        ("no weakness filter", dict(weak=False)),
        ("hold 8c (2h)", dict(hold=8)),
        ("hold 24c (6h)", dict(hold=24)),
        ("hold 32c (8h)", dict(hold=32)),
        ("hold 96c (24h)", dict(hold=96)),
        ("stop +1% buffer", dict(stop="buf1")),
        ("no stop (time exit only)", dict(stop="none")),
    ]
    summs = []
    base_trades = None
    for label, kw in variants:
        s, tdf = run_variant(tickers, label, **kw)
        summs.append(s)
        if label.startswith("BASELINE"):
            base_trades = tdf

    p("")
    p("-" * 78)
    p("B. EXECUTION / COST STRESS")
    for label, kw in [
        ("costs x1.5", dict(cost_mult=1.5)),
        ("costs x2", dict(cost_mult=2.0)),
        ("costs x3", dict(cost_mult=3.0)),
        ("entry at next open (delayed)", dict(delay=True)),
        ("delayed + costs x2", dict(delay=True, cost_mult=2.0)),
        ("loose (10%/1.5x) + costs x2", dict(runup=0.10, volx=1.5, cost_mult=2.0)),
    ]:
        s, _ = run_variant(tickers, label, **kw)
        summs.append(s)

    pd.DataFrame(summs).to_csv("backtest/ps_robustness_variants.csv", index=False)

    bt = base_trades
    nets = bt["net"].to_numpy()
    rng = np.random.default_rng(7)

    p("")
    p("-" * 78)
    p("C. BOOTSTRAP CI ON BASELINE (10,000 resamples of net/trade)")
    bs = np.array([rng.choice(nets, len(nets)).mean() for _ in range(10_000)])
    p(f"pooled net/trade {nets.mean()*100:+.3f}% | 95% CI [{np.percentile(bs,2.5)*100:+.3f}%, "
      f"{np.percentile(bs,97.5)*100:+.3f}%] | P(mean<=0) = {(bs <= 0).mean()*100:.2f}%")

    p("")
    p("D. LEAVE-ONE-OUT (trade-level, baseline)")
    for w in bt["window"].unique():
        sub = bt[bt["window"] != w]["net"]
        p(f"  drop {w:10s}: {len(sub):3d} trades, net/trade {sub.mean()*100:+.3f}%")
    for tk in bt.groupby("ticker")["pnl"].sum().abs().sort_values(ascending=False).head(5).index:
        sub = bt[bt["ticker"] != tk]["net"]
        p(f"  drop {tk:10s}: {len(sub):3d} trades, net/trade {sub.mean()*100:+.3f}%")

    p("")
    p("E. RANDOM-SHORT PLACEBO (matched counts/window, 200 reps)")
    counts = bt.groupby("window").size().to_dict()
    pl = placebo(tickers, counts, 200, rng)
    pct = (pl < nets.mean()).mean() * 100
    p(f"placebo net/trade: mean {pl.mean()*100:+.3f}%, 95th pct {np.percentile(pl,95)*100:+.3f}% | "
      f"actual {nets.mean()*100:+.3f}% beats {pct:.1f}% of placebo runs")

    p("")
    p("F. REGIME SPLIT (BTC 4h EMA20 vs EMA50 at signal time, baseline)")
    bt = bt.copy()
    bt["bull"] = [regime_at(t) for t in bt["t"]]
    for lab, sub in bt.groupby("bull"):
        p(f"  {'bull' if lab else 'bear'}: {len(sub):3d} trades, net/trade {sub['net'].mean()*100:+.3f}%, "
          f"win {(sub['net']>0).mean()*100:.0f}%")

    fname = f"reports/pump_short_robustness_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
