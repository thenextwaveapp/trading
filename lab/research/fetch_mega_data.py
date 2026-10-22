#!/usr/bin/env python3
"""Fetch the MEGA dataset: every USDT perp ever listed on Binance futures
(900 symbols incl. delisted — no survivorship bias), two phases:

  era20: 2020-01 .. 2022-12  — COVID crash, 2021 pump mania, 2022 bear.
         -> backtest/era20_15m.csv.gz, backtest/era20_1h.csv.gz
  wide:  2023-01 .. 2026-09  — universe expansion for the known eras,
         symbols NOT already in paper/universe60.json (merge at load time).
         -> backtest/wide_15m.csv.gz, backtest/wide_1h.csv.gz

Monthly zips from data.binance.vision (free, no key). Resumable: progress
in backtest/mega_manifest.json; finished symbols are skipped on rerun.
Multi-member gzip output (pandas reads it transparently).

Usage: python3 fetch_mega_data.py [era20|wide|both]
"""
import csv
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

FILES = "https://data.binance.vision/"
HDR = ["ticker", "symbol", "t", "o", "h", "l", "c", "v", "n", "taker_buy_v"]
MANIFEST = "backtest/mega_manifest.json"
WORKERS = 8

PHASES = {
    "era20": dict(months=[f"{y}-{m:02d}" for y in (2020, 2021, 2022)
                          for m in range(1, 13)],
                  out="backtest/era20", exclude=set()),
    "wide": dict(months=[f"{y}-{m:02d}" for y in (2023, 2024, 2025, 2026)
                         for m in range(1, 13)][: 12 * 3 + 9],
                 out="backtest/wide",
                 exclude=set(json.load(open("paper/universe60.json")).values())),
}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code < 500:
                return None
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def month_rows(symbol, interval, month):
    blob = get(f"{FILES}data/futures/um/monthly/klines/{symbol}/{interval}/"
               f"{symbol}-{interval}-{month}.zip")
    if blob is None:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            with z.open(z.namelist()[0]) as f:
                rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8")))
    except Exception:
        return []
    out = []
    tk = symbol[:-4]
    for r in rows:
        if not r or not r[0].strip().lstrip("-").isdigit():
            continue
        t = int(float(r[0]))
        if t > 10 ** 14:          # some archives use microseconds
            t //= 1000
        out.append([tk, symbol, t, r[1], r[2], r[3], r[4], r[5], r[8], r[9]])
    return out


def fetch_symbol(symbol, months):
    """Returns {interval: rows}. Probes 15m first — if a symbol has nothing
    in the window at all, skips the 1h pass early."""
    data = {}
    for interval in ("15m", "1h"):
        rows = []
        for m in months:
            rows += month_rows(symbol, interval, m)
        data[interval] = rows
        if interval == "15m" and not rows:
            data["1h"] = []
            break
    return data


def load_manifest():
    try:
        return json.load(open(MANIFEST))
    except FileNotFoundError:
        return {}


def save_manifest(m):
    tmp = MANIFEST + f".tmp{os.getpid()}"
    json.dump(m, open(tmp, "w"))
    os.replace(tmp, MANIFEST)


def append_gz(path, rows, write_header=False):
    with gzip.open(path, "at", newline="") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(HDR)
        w.writerows(rows)


def run_phase(phase):
    cfg = PHASES[phase]
    symbols = json.load(open("backtest/all_usdt_perps.json"))
    symbols = [s for s in symbols if s not in cfg["exclude"]]
    manifest = load_manifest()
    done = manifest.setdefault(phase, {})
    todo = [s for s in symbols if s not in done]
    p15, p1h = cfg["out"] + "_15m.csv.gz", cfg["out"] + "_1h.csv.gz"
    for p in (p15, p1h):
        if not os.path.exists(p):
            append_gz(p, [], write_header=True)
    print(f"[{phase}] {len(symbols)} symbols, {len(done)} done, "
          f"{len(todo)} to fetch, months {cfg['months'][0]}..{cfg['months'][-1]}",
          flush=True)
    t0 = time.time()
    n_done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_symbol, s, cfg["months"]): s for s in todo}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                data = fut.result()
            except Exception as e:
                print(f"[{phase}] {s}: ERROR {e}", flush=True)
                continue
            if data["15m"]:
                append_gz(p15, data["15m"])
                append_gz(p1h, data["1h"])
            done[s] = len(data["15m"])
            n_done += 1
            if n_done % 10 == 0:
                save_manifest(manifest)
            el = time.time() - t0
            eta = el / n_done * (len(todo) - n_done) / 60
            print(f"[{phase}] {s}: {len(data['15m'])} x15m "
                  f"({n_done}/{len(todo)}, eta {eta:.0f}m)", flush=True)
    save_manifest(manifest)
    with_data = sum(1 for v in done.values() if v)
    print(f"[{phase}] DONE — {with_data}/{len(symbols)} symbols had data",
          flush=True)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which not in ("era20", "wide", "both"):
        sys.exit("usage: fetch_mega_data.py [era20|wide|both]")
    for ph in (["era20", "wide"] if which == "both" else [which]):
        run_phase(ph)
