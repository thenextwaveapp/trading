#!/usr/bin/env python3
"""One-shot: seed paper/fleet/pump_events.json from the local candle cache so
the gate30 variant's regime dial is warm immediately instead of needing ~2
weeks of live events. Detection logic mirrors paper_fleet.detect_events /
regime_switch_backtest.pump_events exactly.

Cache ends 2026-10-03; events in the final 24h stay unresolved and the live
fleet resolves them lazily. The 2-day gap to today is accepted (~7% of the
30d window).

Usage: python3 seed_pump_events.py
"""
import json
import time

import numpy as np
import pandas as pd

from backtest import M15
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from runtime.paper_fleet import EVENTS, GATE_FWD, GATE_COOLDOWN, GATE_WINDOW, gate_state

now = int(time.time() * 1000)
cut = now - GATE_WINDOW - 5 * 86_400_000

c15 = pd.read_csv("backtest/r60_candles_15m.csv.gz")
c15 = c15[c15["t"] >= cut - 20 * M15]

events, last_ev = [], {}
for tk, g in c15.groupby("ticker"):
    g = g.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    t = g["t"].to_numpy(np.int64)
    c, h, l, v = (g[k].to_numpy(float) for k in "chlv")
    last = -10**18
    for i in range(16, len(t)):
        if t[i] < cut or t[i] - last < GATE_COOLDOWN:
            continue
        if t[i] - t[i - 16] != 16 * M15:
            continue
        if (v[max(0, i - 8):i + 1] <= 0).any() or h[i] == l[i]:
            continue
        if c[i] / c[i - 16] - 1 < 0.12:
            continue
        fwd = None
        if i + GATE_FWD < len(t) and t[i + GATE_FWD] - t[i] == GATE_FWD * M15:
            fwd = c[i + GATE_FWD] / c[i] - 1
        events.append(dict(tk=tk, t=int(t[i]), px=float(c[i]),
                           fwd=fwd, tries=0))
        last = t[i]
        last_ev[tk] = int(t[i])

events.sort(key=lambda e: e["t"])
store = dict(events=events, last_ev=last_ev)
json.dump(store, open(EVENTS, "w"))
g = gate_state(store)
m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
print(f"seeded {len(events)} events "
      f"({sum(1 for e in events if e['fwd'] is not None)} resolved) -> {EVENTS}")
print(f"gate now: {'SHORT' if g['short'] else 'FLAT'} (n={g['n']}, m={m})")
