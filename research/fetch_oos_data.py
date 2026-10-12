#!/usr/bin/env python3
"""Fetch 15m + 1h candles for the 60-ticker rules universe over 2023-01-01 ->
2024-12-14 — the period BEFORE all existing backtests, untouched by any
analysis in this project. For the out-of-sample variants run.
Outputs: backtest/r60_oos_15m.csv.gz, backtest/r60_oos_1h.csv.gz
"""
import csv
import gzip
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "bn")
from invo_binance_data import klines, ms, norm_ts  # noqa: E402

UNIVERSE = json.load(open("paper/universe60.json"))
START = ms("2023-01-01T00:00:00Z")
END = ms("2024-12-14T23:59:59Z")


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
    for interval, fname in [("1h", "backtest/r60_oos_1h.csv.gz"),
                            ("15m", "backtest/r60_oos_15m.csv.gz")]:
        jobs = [(tk, sym, interval) for tk, sym in UNIVERSE.items()]
        with ThreadPoolExecutor(max_workers=6) as ex:
            results = dict(ex.map(fetch_one, jobs))
        with gzip.open(fname, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(hdr)
            for tk in UNIVERSE:
                w.writerows(results.get(tk, []))
    print("done")


if __name__ == "__main__":
    main()
