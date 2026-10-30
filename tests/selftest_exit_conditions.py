"""Exit-conditions parity — the backtest and the live fleet resolve the same trade.

core.backtest.exit_trade now executes a discretionary `exit_conditions` tree:
it closes the position on the bar the tree first fires (at that bar's close),
after the hard risk exits (stop, take-profit) have had their say. The live fleet
(runtime.spec_runtime.run_exits_spec) runs that SAME exit_trade, but over a fresh
post-signal fetch rather than the full history — so parity only holds if the
tree's indicators are warmed with the same pre-entry bars.

This test builds positions whose exit tree is a 16-bar ROC turning negative (a
real lookback, so warm-up actually matters), then compares:

  backtest path — full candles, position keeps its entry index `i`;
  live path     — entry index dropped, candles fetched from t_sig - (L+1) bars
                  and located by bisect, exactly as run_exits_spec does.

They must return identical (net, exit_t, kind). A divergence means a bot would
exit differently live than it backtested — the one thing this engine promises
never happens.

Run: python3 -m tests.selftest_exit_conditions
"""
import math
import random

from core.backtest import build_position, exit_trade
from core.evaluator import entry_signal
from core.strategy import parse

M15 = 900_000
TAKER = 0.00045
SLIP = 0.0005
T0 = 1_700_000_000_000


def gen_walk(seed, n=260, px0=100.0):
    r = random.Random(seed)
    out, px = [], px0
    for i in range(n):
        o = px
        px = max(px * math.exp(r.gauss(0, 0.03)), 1e-6)
        hi = max(o, px) * (1 + abs(r.gauss(0, 0.012)))
        lo = min(o, px) * (1 - abs(r.gauss(0, 0.012)))
        out.append(dict(t=T0 + i * M15, o=o, h=hi, l=lo, c=px,
                        v=max(r.lognormvariate(10, 0.6), 1.0)))
    return out


def make_spec(side):
    # Enter whenever price is positive (fires every live bar); exit when the
    # 16-bar ROC turns negative. ROC's lookback is what the live fetch must warm.
    return parse({
        "name": "ec", "side": side, "timeframe": "15m",
        "entry": {"logic": "AND", "children": [
            {"left": {"ind": "close"}, "op": "gt", "right": 0}]},
        "exit": {"time_bars": 20,
                 "stop": {"mode": "dstop", "param": 0.08},
                 "exit_conditions": {"logic": "AND", "children": [
                     {"left": {"ind": "ROC", "params": {"period": 16}},
                      "op": "lt", "right": 0}]}},
    })


def live_resolve(pos, candles):
    """Reproduce runtime.spec_runtime.run_exits_spec's fetch + exit exactly:
    drop the entry index, fetch from t_sig - (L+1) bars, resolve by bisect."""
    tape_pos = {k: v for k, v in pos.items() if k != "i"}
    L = pos.get("exit_lookback", 0) if pos.get("exit_conditions") else 0
    step = pos.get("interval_ms", M15)
    start_t = tape_pos["t_sig"] - (L + 1) * step if L else tape_pos["t_sig"]
    limit = min(tape_pos["hold"] + 8 + ((L + 1) if L else 0), 1500)
    slice_ = [c for c in candles if c["t"] >= start_t][:limit]
    return exit_trade(tape_pos, slice_, TAKER, SLIP)


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    total = resolved = mism = 0
    kinds = {}
    for side in ("long", "short"):
        strat = make_spec(side)
        for seed in range(40):
            candles = gen_walk(seed)
            cache = {}
            for i in range(30, len(candles) - 25):
                sig = entry_signal(strat, candles, i, cache)
                if sig is None:
                    continue
                pos = build_position(strat, candles, i, sig)
                if "exit_conditions" not in pos:
                    check(False, "build_position dropped exit_conditions")
                    return 1
                bt = exit_trade(pos, candles, TAKER, SLIP)        # keeps "i"
                live = live_resolve(pos, candles)                 # bisect path
                total += 1
                if bt is not None:
                    resolved += 1
                    kinds[bt[2]] = kinds.get(bt[2], 0) + 1
                if (bt is None) != (live is None):
                    mism += 1
                    if mism <= 5:
                        print(f"  MISMATCH None-ness side={side} seed={seed} "
                              f"i={i} bt={bt} live={live}")
                elif bt is not None:
                    if (abs(bt[0] - live[0]) > 1e-12 or bt[1] != live[1]
                            or bt[2] != live[2]):
                        mism += 1
                        if mism <= 5:
                            print(f"  MISMATCH side={side} seed={seed} i={i} "
                                  f"bt={bt} live={live}")

    print(f"  positions compared: {total}   resolved: {resolved}   "
          f"by kind: {kinds}")
    check(resolved > 0, "test was vacuous — no position ever resolved")
    check(kinds.get("cond", 0) > 0,
          "no position exited on the exit_conditions tree — test is not "
          "exercising the new path")
    check(mism == 0,
          f"{mism} position(s) resolved differently live vs backtest")
    if ok:
        print("\nPASS: exit_conditions resolves identically in backtest and "
              "the live fetch path (warmed history parity).")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
