#!/usr/bin/env python3
"""Fetch CONTINUOUS 15m + 1h Binance futures candles for the backtest universe.
Window: 2026-07-15 -> 2026-10-04 (warmup + threshold calibration + out-of-time test).
Reuses the downloader from bn/invo_binance_data.py.
Outputs: backtest/bt_candles_15m.csv.gz, backtest/bt_candles_1h.csv.gz
"""
import csv
import gzip
import os
import sys

sys.path.insert(0, "bn")
from invo_binance_data import klines, ms, norm_ts  # noqa: E402

UNIVERSE = {  # ticker -> binance symbol (top-22 recent, RAY/ALPACA-type problems excluded)
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT",
    "PUMP": "PUMPUSDT", "ZEC": "ZECUSDT", "HYPE": "HYPEUSDT", "NEAR": "NEARUSDT",
    "WLD": "WLDUSDT", "ONDO": "ONDOUSDT", "SUI": "SUIUSDT", "ARB": "ARBUSDT",
    "AAVE": "AAVEUSDT", "ENA": "ENAUSDT", "KAITO": "KAITOUSDT", "DOGE": "DOGEUSDT",
    "UNI": "UNIUSDT", "ADA": "ADAUSDT", "kPEPE": "1000PEPEUSDT",
    "FARTCOIN": "FARTCOINUSDT", "CRV": "CRVUSDT", "LINK": "LINKUSDT",
}
START = ms("2026-07-15T00:00:00Z")
END = ms("2026-10-04T23:59:59Z")

def main():
    os.makedirs("backtest", exist_ok=True)
    hdr = ["ticker", "symbol", "t", "o", "h", "l", "c", "v", "n", "taker_buy_v"]
    for interval, fname in [("1h", "backtest/bt_candles_1h.csv.gz"), ("15m", "backtest/bt_candles_15m.csv.gz")]:
        with gzip.open(fname, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(hdr)
            for tk, sym in UNIVERSE.items():
                rows = klines(sym, interval, [(START, END)]) or []
                kept = 0
                for r in rows:
                    t = norm_ts(r[0])
                    if START <= t <= END:
                        w.writerow([tk, sym, t, r[1], r[2], r[3], r[4], r[5], r[8], r[9]])
                        kept += 1
                print(f"{interval} {tk}: {kept} candles", flush=True)
    print("done")


if __name__ == "__main__":
    main()
