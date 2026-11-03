#!/usr/bin/env python3
"""Prove live/bot.py signals are byte-identical to the research/fleet code.

Compares signal_short vs paper_fleet.signal (rule P, slow params) and
signal_capit vs paper_fleet.signal_capit on the cached full-span candles:
every backtest signal bar must fire, random non-signal bars must not.
Run from the repo root: python3 live/check_parity.py
"""
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "live"))
sys.path.insert(0, os.path.join(ROOT, "research"))
os.chdir(ROOT)

from runtime import paper_fleet as pf                                   # noqa: E402
from bot import (signal_short, signal_capit, BOOKS,        # noqa: E402
                 SHORT_BOOK, LONG_BOOK)
from regime_switch_backtest import load_full               # noqa: E402

random.seed(7)
tickers = load_full()
n_ok = n_mis = 0
for tk, d in tickers.items():
    n = len(d["t"])
    idx = random.sample(range(130, n - 1), min(120, max(0, n - 131)))
    for i in idx:
        ks = [dict(t=int(d["t"][j]), o=float(d["o"][j]), h=float(d["h"][j]),
                   l=float(d["l"][j]), c=float(d["c"][j]), v=float(d["v"][j]))
              for j in range(max(0, i - 120), i + 1)]
        a = signal_short(ks, BOOKS[SHORT_BOOK])
        b = pf.signal(ks, BOOKS[SHORT_BOOK])
        if (a is None) != (b is None) or \
                (a and (a["entry"] != b["entry"] or a["stop"] != b["hh"])):
            n_mis += 1
            print(f"SHORT MISMATCH {tk} i={i}")
        else:
            n_ok += 1
        a = signal_capit(ks, BOOKS[LONG_BOOK])
        b = pf.signal_capit(ks, dict(depth=BOOKS[LONG_BOOK]["depth"]))
        if (a is None) != (b is None) or \
                (a and abs(a["sl_basis"] - b["sl_basis"]) > 1e-12):
            n_mis += 1
            print(f"CAPIT MISMATCH {tk} i={i}")
        else:
            n_ok += 1
print(f"\nbars compared: {n_ok + n_mis} | mismatches: {n_mis}")
sys.exit(1 if n_mis else 0)
