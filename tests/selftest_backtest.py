"""Differential test for the backtest engine.

Reuses the vendored legacy signal functions and candle generators from
core.selftest, vendors paper_fleet.check_exit verbatim, and builds an
independent reference backtest loop. Then asserts the new backtest() produces
an identical trade ledger (signal time, exit time, kind, net return) on the
same candles — for Rule P (hh stop + time) and capit (no stop + time).

Run:  python3 -m core.selftest_backtest
"""
import sys

from core import parse
from core.backtest import backtest, DEFAULTS
from core.presets import RULE_P, CAPIT
from .selftest import (legacy_signal, legacy_signal_capit,
                           gen_random, craft_pump, craft_capit)

M15 = 900_000
TAKER, SLIP = DEFAULTS["taker"], DEFAULTS["slip"]


# --- vendored legacy exit (verbatim from paper_fleet.check_exit) ----------
def legacy_check_exit(pos, candles):
    entry, hold = pos["entry"], pos["hold"]
    side = pos.get("side", -1)
    level, low_min = pos["stop"], entry
    trail_k = pos.get("trail_k")
    natr = pos.get("natr")
    tp = pos.get("tp")
    post = [k for k in candles if k["t"] >= pos["t_sig"]][:hold]
    for n, k in enumerate(post, 1):
        if (k["h"] > level) if side < 0 else (k["l"] < level):
            net = side * (level / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "sl"
        if tp and pos.get("tp_close"):
            if (k["c"] <= tp) if side < 0 else (k["c"] >= tp):
                net = side * (k["c"] / entry - 1) - (2 * TAKER + SLIP)
                return net, k["t"] + M15, "tp"
        elif tp and ((k["l"] <= tp) if side < 0 else (k["h"] >= tp)):
            net = side * (tp / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "tp"
        if side < 0 and trail_k and natr:
            low_min = min(low_min, k["l"])
            level = min(level, low_min * (1 + trail_k * natr))
        if n == hold:
            net = side * (k["c"] / entry - 1) - (2 * TAKER + SLIP)
            return net, k["t"] + M15, "time"
    return None


# --- independent reference loops ------------------------------------------
def ref_backtest(candles, legacy_sig, cfg, side, hold, stop_of, start):
    trades, open_until = [], -1
    for i in range(start, len(candles)):
        sig = legacy_sig(candles[:i + 1], cfg)
        if not sig or sig["t_sig"] < open_until:
            continue
        pos = {"entry": sig["entry"], "hold": hold, "side": side,
               "stop": stop_of(sig), "t_sig": sig["t_sig"]}
        ex = legacy_check_exit(pos, candles)
        if ex is None:
            continue
        net, exit_t, kind = ex
        trades.append({"t_sig": sig["t_sig"], "exit_t": exit_t,
                       "kind": kind, "net": net})
        open_until = exit_t
    return trades


def ledger_key(t):
    return (t["t_sig"], t["exit_t"], t["kind"], round(t["net"], 10))


def compare(label, strategy, candles, legacy_sig, cfg, side, hold, stop_of):
    # compare past a shared warmup, clear of the legacy len>=21/98 cushion
    start = strategy["_lookback"] + 8
    new = backtest(strategy, candles, start=start)["trades"]
    ref = ref_backtest(candles, legacy_sig, cfg, side, hold, stop_of, start)
    nk = [ledger_key(t) for t in new]
    rk = [ledger_key(t) for t in ref]
    ok = nk == rk
    return label, len(ref), ok, (nk, rk)


def main():
    base = parse(RULE_P)
    capit = parse(CAPIT)
    cfg_base = {"runup": 0.12, "vol": 2.0}
    cfg_capit = {"depth": 0.2}

    jobs = []
    for seed in range(12):
        c = gen_random(seed, n=700)
        jobs.append(compare(f"random#{seed} pump", base, c, legacy_signal,
                            cfg_base, -1, 16, lambda s: s["hh"]))
        jobs.append(compare(f"random#{seed} capit", capit, c,
                            legacy_signal_capit, cfg_capit, 1, 96,
                            lambda s: 0.0))
    jobs.append(compare("craft pump", base, craft_pump(), legacy_signal,
                        cfg_base, -1, 16, lambda s: s["hh"]))
    jobs.append(compare("craft capit", capit, craft_capit(),
                        legacy_signal_capit, cfg_capit, 1, 96, lambda s: 0.0))

    total_trades = sum(j[1] for j in jobs)
    bad = [j for j in jobs if not j[2]]
    for label, ntr, ok, _ in jobs:
        print(f"  [{'OK ' if ok else 'FAIL'}] {label:22s} trades={ntr:3d}")

    print(f"\n  trades compared: {total_trades}")
    if total_trades == 0:
        print("\nFAIL: vacuous — no trades generated.")
        return 1
    if bad:
        for label, _, _, (nk, rk) in bad:
            print(f"\n  {label} diverged:\n    new={nk[:6]}\n    ref={rk[:6]}")
        return 1
    print("\nPASS: backtest engine reproduces the legacy entry+exit ledger "
          "(signal time, exit time, kind, net) trade-for-trade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
