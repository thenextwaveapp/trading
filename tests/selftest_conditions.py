"""Weather condition buckets — ledger -> nine regime cells.

Run: python3 -m tests.selftest_conditions
"""
from core.conditions import cell_at, conditions_breakdown, VOLS, TRENDS
from runtime.spec_runtime import _weather_ok
from .selftest import gen_random

M15 = 900_000


def main():
    btc = gen_random(11, n=900)
    nets = [0.02, -0.01, 0.04, 0.015]
    trades = [
        {"t_sig": btc[i]["t"] + M15, "net": net}
        for i, net in zip((250, 400, 600, 850), nets)
    ]

    cells = conditions_breakdown(trades, {"BTC": btc})
    ok = True

    if len(cells) != 9:
        print(f"FAIL: expected 9 cells, got {len(cells)}")
        return 1
    got = {(c["volatility"], c["btc_trend"]) for c in cells}
    want = {(v, t) for v in VOLS for t in TRENDS}
    if got != want:
        print(f"FAIL: cells mismatch: {got ^ want}")
        ok = False

    total = sum(c["trades"] for c in cells)
    if total != len(trades):
        print(f"FAIL: counted {total} trades, expected {len(trades)}")
        ok = False

    weighted = sum((c["return_per_trade"] or 0) * c["trades"] for c in cells)
    mean = sum(nets) / len(nets) * 100
    if total and abs(weighted / total - mean) > 1e-9:
        print(f"FAIL: weighted {weighted / total}% != mean {mean}%")
        ok = False

    current = [c for c in cells if c["is_current"]]
    if len(current) != 1:
        print(f"FAIL: expected one current cell, got {len(current)}")
        ok = False

    lo, hi = cells[0]["vol_lo"], cells[0]["vol_hi"]
    if lo is None or hi is None:
        print("FAIL: cells should carry the training terciles")
        ok = False
    elif current and cell_at(btc, None, lo, hi) != (current[0]["volatility"], current[0]["btc_trend"]):
        print(f"FAIL: live cell {cell_at(btc, None, lo, hi)} != "
              f"{(current[0]['volatility'], current[0]['btc_trend'])}")
        ok = False

    if not conditions_breakdown(trades, {}):
        print("OK: no BTC -> no invented weather cells")
    else:
        print("FAIL: conditions without BTC should be empty")
        ok = False

    if current:
        key = f"{current[0]['volatility']}:{current[0]['btc_trend']}"
        other = next(f"{v}:{t}" for v in VOLS for t in TRENDS if f"{v}:{t}" != key)
        gate = {"restrict": True, "cells": [key], "vol_lo": lo, "vol_hi": hi}
        if not _weather_ok(gate, btc, None)[0]:
            print("FAIL: gate should allow the current cell")
            ok = False
        if _weather_ok({**gate, "cells": [other]}, btc, None)[0]:
            print("FAIL: gate should block an unselected cell")
            ok = False
        if not _weather_ok({"restrict": True, "cells": [other]}, btc, None)[0]:
            print("FAIL: legacy gate without terciles should stay open")
            ok = False
        if _weather_ok(gate, None, None)[0]:
            print("FAIL: gate without BTC data must block")
            ok = False

    if ok:
        print(f"PASS: {total} trades across 9 cells, current="
              f"{current[0]['volatility']}:{current[0]['btc_trend']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
