#!/usr/bin/env python3
"""FLEET RACE, MAJORS EDITION — every fleet_config.json variant on the 10
majors (capit_maj's list), 2020-01 -> 2026-10 (era20 + oos + main caches
stitched per ticker). Engines/account model identical to fleet_race.py.

Usage: python3 research/fleet_race_majors.py
Writes: reports/fleet_race_majors_<stamp>.txt
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backtest import H
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL
from fleet_race import sig_pump_rows, sig_capit_rows, sig_hourly_rows, race

MAJORS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK",
          "AVAX", "LTC"]
PAIRS = [("backtest/era20_15m.csv.gz", "backtest/era20_1h.csv.gz"),
         ("backtest/r60_oos_15m.csv.gz", "backtest/r60_oos_1h.csv.gz"),
         ("backtest/r60_candles_15m.csv.gz", "backtest/r60_candles_1h.csv.gz")]
USECOLS = ["ticker", "t", "o", "h", "l", "c", "v"]

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def load_majors():
    """Stitched per-ticker arrays across all three cache eras, shaped like
    rules_backtest.load, + regime_at from the merged BTC 1h series."""
    f15, f1h = {tk: [] for tk in MAJORS}, {tk: [] for tk in MAJORS}
    for c15, c1 in PAIRS:
        for path, acc in [(c15, f15), (c1, f1h)]:
            for ch in pd.read_csv(path, usecols=USECOLS, chunksize=4_000_000):
                ch = ch[ch["ticker"].isin(MAJORS)]
                for tk, g in ch.groupby("ticker"):
                    acc[tk].append(g)
    tickers, btc_1h = {}, None
    for tk in MAJORS:
        if not f15[tk] or not f1h[tk]:
            continue
        g = pd.concat(f15[tk]).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        g1 = pd.concat(f1h[tk]).drop_duplicates("t").sort_values("t") \
            .reset_index(drop=True)
        if tk == "BTC":
            btc_1h = g1
        if len(g) < 500 or len(g1) < 100:
            continue
        t = g["t"].to_numpy(np.int64)
        o, hh, ll, c, v = (g[k].to_numpy(float) for k in "ohlcv")
        prev = np.concatenate([[g1["c"].iloc[0]], g1["c"].to_numpy()[:-1]])
        tr = np.maximum(g1["h"].to_numpy(), prev) - \
            np.minimum(g1["l"].to_numpy(), prev)
        natr24 = pd.Series(tr).rolling(24).mean().to_numpy() / g1["c"].to_numpy()
        tickers[tk] = dict(t=t, o=o, h=hh, l=ll, c=c, v=v,
                           natr_t=(g1["t"] + H).to_numpy(), natr=natr24)
    s = btc_1h.set_index("t")["c"].groupby(lambda x: x - x % (4 * H)).last()
    e20 = s.ewm(span=20, adjust=False).mean()
    e50 = s.ewm(span=50, adjust=False).mean()
    rt = s.index.to_numpy() + 4 * H
    rb = (e20 > e50).to_numpy()

    def regime_at(tsv):
        i = np.searchsorted(rt, tsv, "right") - 1
        return None if i < 0 else bool(rb[i])
    return tickers, regime_at


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FLEET RACE, MAJORS — {stamp} | {len(MAJORS)} majors, "
      "2020-01 .. 2026-10 (three caches stitched)")
    p("same engines/account model as fleet_race.py")
    p("")

    tickers, regime_at = load_majors()
    t0 = min(d["t"][0] for d in tickers.values())
    t1 = max(d["t"][-1] for d in tickers.values())
    for d in tickers.values():
        precompute(d)
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)
    p(f"loaded {len(tickers)} majors "
      f"({pd.to_datetime(int(t0), unit='ms').date()} .. "
      f"{pd.to_datetime(int(t1), unit='ms').date()}) | "
      f"pump events {len(ev[0]):,}")
    p("")
    p(f"{'variant':12s} {'$10k ->':>11s} {'ret%':>8s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg net':>8s}")

    cfgs = json.load(open("fleet_config.json"))["strategies"]
    results = []
    for sk, s in cfgs.items():
        for vn, v in s["variants"].items():
            cfg = {k: x for k, x in v.items() if k not in ("bt", "note")}
            cfg["stop"] = tuple(cfg["stop"]) if "stop" in cfg else ("none", 0)
            if cfg.get("engine") == "super":
                eq, maxdd, n_s, n_c, sk_, lq = SL.run_book(
                    tickers, dial, regime_at,
                    {k: tuple(x) for k, x in cfg["sizing"].items()})
                results.append((vn, eq, maxdd))
                p(f"{vn:12s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
                  f"{maxdd*100:6.1f}% {n_s + n_c:6d} {'':>5s} {'':>8s}  *margin engine")
                continue
            if cfg.get("engine") in ("churn", "loser"):
                rows = sig_hourly_rows(tickers, cfg)
            elif cfg.get("engine") == "capit":
                rows = sig_capit_rows(tickers, cfg, regime_at)
            else:
                rows = sig_pump_rows(tickers, cfg, dial)
            eq, maxdd, n, avg, win = race(tickers, rows, cfg)
            results.append((vn, eq, maxdd))
            p(f"{vn:12s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
              f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+7.2f}%")

    p("")
    p("podium (by final equity):")
    for vn, eq, maxdd in sorted(results, key=lambda r: -r[1])[:5]:
        p(f"  {vn:12s} ${eq:,.0f}  (dd {maxdd*100:.1f}%)")

    fname = ("reports/fleet_race_majors_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
