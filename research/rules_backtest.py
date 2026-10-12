#!/usr/bin/env python3
"""Rule-based walk-forward: pump-short (P) and drift-long (D), per
reports/rules_preregistration.md. No ML, no calibration — rules are frozen.

Usage: python3 rules_backtest.py
Writes: reports/rules_backtest_<stamp>.txt, backtest/trades_rules.csv.gz
"""
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from wf_engine import WINDOWS, ts, metrics, MAX_CONC, RISK, NOTIONAL_CAP, KILL_DD, \
    KILL_LOOKBACK, KILL_PAUSE
from backtest import M15, H

TAKER = 0.00045
SLIP = 0.0005

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def load(c15_path, c1_path):
    c15 = pd.read_csv(c15_path)
    c1 = pd.read_csv(c1_path)
    b = c1[c1["ticker"] == "BTC"].drop_duplicates("t").sort_values("t")
    b4 = b.set_index("t")["c"].groupby(lambda t: t - t % (4 * H)).last()
    e20 = b4.ewm(span=20, adjust=False).mean()
    e50 = b4.ewm(span=50, adjust=False).mean()
    regime_t = b4.index.to_numpy() + 4 * H
    regime_bull = (e20 > e50).to_numpy()

    def regime_at(tsv):
        i = np.searchsorted(regime_t, tsv, "right") - 1
        return None if i < 0 else bool(regime_bull[i])

    tickers = {}
    for tk, g in c15.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t").reset_index(drop=True)
        g1 = c1[c1["ticker"] == tk].drop_duplicates("t").sort_values("t").reset_index(drop=True)
        if len(g) < 500 or len(g1) < 100:
            continue
        t = g["t"].to_numpy(np.int64)
        o, hh, ll, c, v = (g[k].to_numpy(float) for k in "ohlcv")
        prev = np.concatenate([[g1["c"].iloc[0]], g1["c"].to_numpy()[:-1]])
        tr = np.maximum(g1["h"].to_numpy(), prev) - np.minimum(g1["l"].to_numpy(), prev)
        natr24 = pd.Series(tr).rolling(24).mean().to_numpy() / g1["c"].to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v,
                           natr_t=(g1["t"] + H).to_numpy(), natr=natr24)
    return tickers, regime_at


def natr_at(d, tsv):
    i = np.searchsorted(d["natr_t"], tsv, "right") - 1
    return d["natr"][i] if i >= 0 and np.isfinite(d["natr"][i]) else None


def alive(d, i):
    if i < 20:
        return False
    t = d["t"]
    if t[i] - t[i - 16] != 16 * M15:
        return False
    vw = d["v"][i - 8:i + 1]
    return (vw > 0).all() and d["h"][i] != d["l"][i]


def signals_P(d, t0, t1):
    t, c, v, hh = d["t"], d["c"], d["v"], d["h"]
    lo = np.searchsorted(t, t0 - M15)
    hi = np.searchsorted(t, t1 - M15)
    out = []
    for i in range(max(lo, 20), hi):
        if not alive(d, i):
            continue
        runup = c[i] / c[i - 16] - 1
        if runup < 0.12 or c[i] >= c[i - 1]:
            continue
        mu = v[i - 8:i].mean()
        if mu <= 0 or v[i] / mu < 2:
            continue
        out.append((t[i] + M15, i, runup))
    return out


def signals_D(d, t0, t1, regime_at):
    t, c = d["t"], d["c"]
    lo = np.searchsorted(t, t0 - M15)
    hi = np.searchsorted(t, t1 - M15)
    out = []
    for i in range(max(lo, 20), hi):
        if not alive(d, i):
            continue
        if abs(c[i] / c[i - 4] - 1) >= 0.01 or abs(c[i] / c[i - 16] - 1) >= 0.03:
            continue
        na = natr_at(d, t[i] + M15)
        if na is None or not (0.008 <= na <= 0.025):
            continue
        if regime_at(t[i] + M15) is not True:
            continue
        out.append((t[i] + M15, i, na))
    return out


def exit_P(d, i, entry):
    """Short from close[i]. Stop = signal-time 4h high; time exit at i+16."""
    sl_level = d["h"][i - 16:i + 1].max()
    for j in range(i + 1, min(i + 17, len(d["t"]))):
        if d["h"][j] > sl_level:
            gross = -(sl_level / entry - 1)
            return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", (sl_level / entry - 1)
    j = min(i + 16, len(d["t"]) - 1)
    gross = -(d["c"][j] / entry - 1)
    return gross - (2 * TAKER + SLIP), d["t"][j] + M15, "time", (sl_level / entry - 1)


def exit_D(d, i, entry, na):
    """Long from close[i]. SL 3x natr24; time exit at i+96."""
    sl = entry * (1 - 3 * na)
    for j in range(i + 1, min(i + 97, len(d["t"]))):
        if d["l"][j] <= sl:
            return (sl / entry - 1) - (2 * TAKER + SLIP), d["t"][j] + M15, "sl", 3 * na
    j = min(i + 96, len(d["t"]) - 1)
    return (d["c"][j] / entry - 1) - (2 * TAKER + SLIP), d["t"][j] + M15, "time", 3 * na


def portfolio(sig_rows, tickers, exit_fn):
    """sig_rows: list of (t_sig, ticker, i, extra). Returns trades, eq_hist."""
    sig_rows.sort()
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
        net, exit_t, kind, sl_dist = exit_fn(d, i, entry, extra) if exit_fn is exit_D \
            else exit_fn(d, i, entry)
        notional = min(RISK * equity / max(abs(sl_dist), 0.005), NOTIONAL_CAP * equity)
        pnl = notional * net
        pending.append((exit_t, pnl))
        open_until[tk] = exit_t
        trades.append(dict(ticker=tk, t=t_sig, kind=kind, net=net, pnl=pnl, extra=extra))
    for et, pnl in sorted(pending):
        equity += pnl
        eq_hist.append((et, equity))
    return trades, eq_hist


def beta_baseline(tickers, t0, t1, n, rng):
    """Random-time longs, 24h hold, same fees — what beta alone earns."""
    nets = []
    tks = list(tickers)
    for _ in range(n * 3):
        tk = tks[rng.integers(len(tks))]
        d = tickers[tk]
        lo = np.searchsorted(d["t"], t0)
        hi = np.searchsorted(d["t"], t1) - 97
        if hi <= lo:
            continue
        i = int(rng.integers(lo, hi))
        if not alive(d, i):
            continue
        nets.append(d["c"][i + 96] / d["c"][i] - 1 - (2 * TAKER + SLIP))
    return float(np.mean(nets)) if nets else np.nan


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")
    p(f"RULES WALK-FORWARD — {stamp} | universe {len(tickers)} tickers | rules frozen per reports/rules_preregistration.md")
    rng = np.random.default_rng(7)
    all_rows, win_stats = [], {"P": [], "D": []}
    for name, a, b in WINDOWS:
        t0, t1 = ts(a), ts(b)
        for rule, sigfn, exfn in [("P", signals_P, exit_P), ("D", None, exit_D)]:
            rows = []
            for tk, d in tickers.items():
                if rule == "P":
                    rows += [(tsg, tk, i, ru) for tsg, i, ru in signals_P(d, t0, t1)]
                else:
                    rows += [(tsg, tk, i, na) for tsg, i, na in signals_D(d, t0, t1, regime_at)]
            trades, eqh = portfolio(rows, tickers, exfn)
            met = metrics(eqh, t0, t1)
            nets = [x["net"] for x in trades]
            base = beta_baseline(tickers, t0, t1, max(len(trades), 30), rng) if rule == "D" else np.nan
            p(f"{name} rule {rule}: signals {len(rows):5,} trades {len(trades):4,} | "
              f"net/trade {np.mean(nets)*100 if nets else 0:+.3f}% | eq {met['ret']*100:+.2f}% "
              f"dd {met['maxdd']*100:.2f}%" + (f" | beta baseline {base*100:+.3f}%" if rule == "D" else ""))
            for x in trades:
                x.update(window=name, rule=rule)
            all_rows += trades
            win_stats[rule].append(dict(window=name, n=len(trades),
                                        net=np.mean(nets) if nets else np.nan,
                                        ret=met["ret"], dd=met["maxdd"], beta=base))
    t = pd.DataFrame(all_rows)
    t.to_csv("backtest/trades_rules.csv.gz", index=False, compression="gzip")
    p("")
    p("=" * 78)
    p("GATE CHECK (pre-registered)")
    for rule in ("P", "D"):
        g = t[t["rule"] == rule]
        ws = pd.DataFrame(win_stats[rule]).dropna(subset=["net"])
        if not len(g):
            p(f"rule {rule}: no trades"); continue
        pooled = g["net"].mean()
        eqs = (1 + ws["ret"]).prod() - 1
        conc = g.groupby("ticker")["pnl"].sum()
        pos = conc[conc > 0].sum()
        top = conc.max() / pos * 100 if pos > 0 else np.nan
        winpos = (ws["ret"] > 0).mean() * 100
        p(f"rule {rule}: trades {len(g):,} | pooled net/trade {pooled*100:+.3f}% | windows+ {winpos:.0f}% "
          f"| compounded {eqs*100:+.2f}% | worst window dd {ws['dd'].min()*100:.1f}% | top ticker {top:.0f}% of +PnL")
        checks = [pooled >= 0.0010, winpos >= 60, ws["dd"].min() >= -0.20, top <= 40]
        if rule == "D":
            edge_over_beta = pooled - ws["beta"].mean()
            p(f"  rule D edge over beta baseline: {edge_over_beta*100:+.3f}%/trade (needs >= +0.10%)")
            checks.append(edge_over_beta >= 0.0010)
        p(f"  -> {'PASS' if all(checks) else 'FAIL'} ({sum(checks)}/{len(checks)} criteria)")
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/rules_backtest_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt"
    with open(fname, "w") as f:
        f.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
