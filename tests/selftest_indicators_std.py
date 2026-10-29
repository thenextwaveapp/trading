"""Pure-Python standard indicators: registered everywhere + match TA-Lib.

Guards core/indicators_std.py. Two things matter:
  1. The standard ids (RSI, EMA, ATR, MACD, …) are ALWAYS in the registry, even
     with no TA-Lib C library — so the training worker / live fleet never hit
     "unknown indicator: 'RSI'".
  2. Where TA-Lib is installed, the common set matches it value-for-value
     (first-valid bar + values), so the switch is transparent. MACD/ADX use the
     canonical definition (TA-Lib's differ by its unstable-period seeding), so
     they're only sanity-checked, not diffed.
"""
import random

import core  # noqa: F401 — registers indicators_std (+ talib_wrap)
from core.indicators import REGISTRY

EXACT = [
    ("SMA", "SMA", 0, False, {"timeperiod": 20}),
    ("EMA", "EMA", 0, False, {"timeperiod": 20}),
    ("WMA", "WMA", 0, False, {"timeperiod": 20}),
    ("DEMA", "DEMA", 0, False, {"timeperiod": 15}),
    ("TEMA", "TEMA", 0, False, {"timeperiod": 10}),
    ("RSI", "RSI", 0, False, {"timeperiod": 14}),
    ("CMO", "CMO", 0, False, {"timeperiod": 14}),
    ("MOM", "MOM", 0, False, {"timeperiod": 10}),
    ("ATR", "ATR", 0, False, {"timeperiod": 14}),
    ("NATR", "NATR", 0, False, {"timeperiod": 14}),
    ("WILLR", "WILLR", 0, False, {"timeperiod": 14}),
    ("CCI", "CCI", 0, False, {"timeperiod": 14}),
    ("MFI", "MFI", 0, False, {"timeperiod": 14}),
    ("OBV", "OBV", 0, False, {}),
    ("BBANDS_upperband", "BBANDS", 0, True, {"timeperiod": 20, "nbdevup": 2.0, "nbdevdn": 2.0}),
    ("BBANDS_middleband", "BBANDS", 1, True, {"timeperiod": 20, "nbdevup": 2.0, "nbdevdn": 2.0}),
    ("BBANDS_lowerband", "BBANDS", 2, True, {"timeperiod": 20, "nbdevup": 2.0, "nbdevdn": 2.0}),
]
SANITY = [
    ("MACD_macd", {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}),
    ("MACD_macdsignal", {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}),
    ("MACD_macdhist", {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}),
    ("ADX", {"timeperiod": 14}),
]


def _candles(n=300, seed=7):
    random.seed(seed)
    px = 100.0
    out = []
    for i in range(n):
        px *= 1 + random.uniform(-0.01, 0.011)
        o = px * (1 + random.uniform(-0.002, 0.002))
        c = px
        h = max(o, c) * (1 + random.uniform(0, 0.004))
        l = min(o, c) * (1 - random.uniform(0, 0.004))
        out.append({"t": i, "o": o, "h": h, "l": l, "c": c, "v": random.uniform(100, 1000)})
    return out


def main() -> int:
    candles = _candles()
    fails = []

    # (1) everything registers and produces values regardless of TA-Lib.
    for ind_id, _t, _i, _m, p in EXACT:
        if ind_id not in REGISTRY:
            fails.append(f"{ind_id} not registered")
            continue
        out = REGISTRY[ind_id].fn(candles, **p)
        if not any(x is not None for x in out):
            fails.append(f"{ind_id} produced no values")
    for ind_id, p in SANITY:
        if ind_id not in REGISTRY:
            fails.append(f"{ind_id} not registered")
            continue
        out = REGISTRY[ind_id].fn(candles, **p)
        if not any(x is not None for x in out):
            fails.append(f"{ind_id} produced no values")

    # (2) if TA-Lib is present, the common set must match it exactly.
    try:
        import numpy as np
        from talib import abstract
        have_talib = True
    except Exception:
        have_talib = False
        print("[indicators_std] TA-Lib not installed — parity check skipped (registration check still ran)")

    if have_talib:
        inp = {k: np.array([x[{"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}[k]] for x in candles])
               for k in ("open", "high", "low", "close", "volume")}
        for ind_id, tname, idx, multi, p in EXACT:
            mine = REGISTRY[ind_id].fn(candles, **p)
            r = abstract.Function(tname)(inp, **p)
            ref = [None if x != x else float(x) for x in (r[idx] if multi else r)]
            fi_m = next((i for i, x in enumerate(mine) if x is not None), None)
            fi_r = next((i for i, x in enumerate(ref) if x is not None), None)
            md = scale = 0.0
            for i in range(len(candles)):
                if mine[i] is not None and ref[i] is not None:
                    md = max(md, abs(mine[i] - ref[i]))
                    scale = max(scale, abs(ref[i]))
            rel = md / scale if scale else md
            if fi_m != fi_r or rel > 1e-6:
                fails.append(f"{ind_id} vs TA-Lib: first {fi_m}/{fi_r} rel={rel:.1e}")

    if fails:
        for f in fails:
            print("  FAIL:", f)
        return 1
    print(f"[indicators_std] {len(EXACT)} exact + {len(SANITY)} canonical indicators OK (talib={'yes' if have_talib else 'no'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
