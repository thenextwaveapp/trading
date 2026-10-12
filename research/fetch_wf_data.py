#!/usr/bin/env python3
"""Fetch continuous 15m + 1h candles for the walk-forward: 2024-12-15 -> 2026-10-04.
Parallel (6 workers). Tickers not yet listed in early windows simply have no data
there (walk-forward uses whatever exists per window).
Outputs: backtest/wf_candles_15m.csv.gz, backtest/wf_candles_1h.csv.gz
"""
import csv
import gzip
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "bn")
from invo_binance_data import klines, ms, norm_ts  # noqa: E402
from fetch_bt_data import UNIVERSE  # noqa: E402

START = ms("2024-12-15T00:00:00Z")
END = ms("2026-10-04T23:59:59Z")


def fetch_one(args):
    tk, sym, interval = args
    rows = klines(sym, interval, [(START, END)]) or []
    out = [[tk, sym, norm_ts(r[0]), r[1], r[2], r[3], r[4], r[5], r[8], r[9]]
           for r in rows if START <= norm_ts(r[0]) <= END]
    print(f"{interval} {tk}: {len(out)} candles", flush=True)
    return tk, out


def main():
    os.makedirs("backtest", exist_ok=True)
    hdr = ["ticker", "symbol", "t", "o", "h", "l", "c", "v", "n", "taker_buy_v"]
    for interval, fname in [("1h", "backtest/wf_candles_1h.csv.gz"),
                            ("15m", "backtest/wf_candles_15m.csv.gz")]:
        jobs = [(tk, sym, interval) for tk, sym in UNIVERSE.items()]
        with ThreadPoolExecutor(max_workers=6) as ex:
            results = dict((tk, out) for tk, out in ex.map(fetch_one, jobs))
        with gzip.open(fname, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(hdr)
            for tk, _, _ in jobs:
                w.writerows(results.get(tk, []))
    print("done")


if __name__ == "__main__":
    main()
