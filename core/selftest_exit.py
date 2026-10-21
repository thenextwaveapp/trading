"""Exit-parity characterization test — the other half of the honesty invariant.

selftest.py proves the composable ENTRY (entry_signal) reproduces the hand-coded
paper_fleet.signal()/signal_capit() bar-for-bar. This proves the composable EXIT
(core.backtest.exit_trade) reproduces the live paper_fleet.check_exit() trade-for-
trade: same (net, exit_t, kind) on every resolved position.

The legacy check_exit is vendored verbatim below (paper_fleet.py lines 439-470) so
the test pins its behaviour with no heavy import. We build positions across every
exit mode core currently ports — stop breach (hh/dstop level), take-profit
(intrabar and close-cross), short trailing ratchet, and the time exit — over
crafted and random candle series, and assert identical resolutions.

Run:  python3 -m core.selftest_exit
"""
import math
import random
import sys

from core.backtest import exit_trade

M15 = 900_000
TAKER = 0.00045
SLIP = 0.0005


# --- vendored legacy exit (verbatim from paper_fleet.py check_exit) -------
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


# NOTE on the level-0 sentinel: legacy check_exit treats a short with stop 0 as
# "instant stop" (k["h"] > 0 is always true) — it is never called that way,
# because the no-stop families are longs (level 0, k["l"] < 0 never true). core's
# exit_trade added an explicit `if level` guard so stop 0 means "no stop" on
# EITHER side. To compare apples to apples we only build no-stop positions as
# longs (how they actually occur live); shorts always carry a real level.


# --- candle generators ----------------------------------------------------
def gen_walk(seed, n=140, start_t=1_600_000_000_000, px0=100.0):
    r = random.Random(seed)
    out, px = [], px0
    for i in range(n):
        o = px
        px = max(px * math.exp(r.gauss(0, 0.03)), 1e-6)
        hi = max(o, px) * (1 + abs(r.gauss(0, 0.015)))
        lo = min(o, px) * (1 - abs(r.gauss(0, 0.015)))
        out.append(dict(t=start_t + i * M15, o=o, h=hi, l=lo, c=px,
                        v=max(r.lognormvariate(10, 0.6), 1.0)))
    return out


def build_positions(candles):
    """One position per entry bar, across every ported exit mode, so the two
    engines are compared over a wide spread of resolutions."""
    t0 = candles[0]["t"]
    out = []
    for i in range(0, len(candles) - 40, 7):
        k = candles[i]
        entry = k["c"]
        t_sig = k["t"] + M15
        base = dict(entry=entry, hold=16, t_sig=t_sig)
        # short, hh-style stop a bit above entry
        out.append(dict(base, side=-1, stop=entry * 1.03))
        # short, tight stop (likely breaches) + intrabar take-profit below
        out.append(dict(base, side=-1, stop=entry * 1.015, tp=entry * 0.96))
        # short, take-profit on CLOSE-cross (loser_tp semantics)
        out.append(dict(base, side=-1, stop=entry * 1.05, tp=entry * 0.97,
                        tp_close=True))
        # short, trailing ratchet
        out.append(dict(base, side=-1, stop=entry * 1.04, trail_k=3.0,
                        natr=0.01))
        # long, disaster stop below entry
        out.append(dict(base, side=1, stop=entry * 0.97))
        # long, no stop (level 0) — time exit only (capit "none" mode)
        out.append(dict(base, side=1, stop=0.0, hold=24))
        # long, take-profit above
        out.append(dict(base, side=1, stop=entry * 0.95, tp=entry * 1.04))
    return out


def main():
    total = mism = resolved = 0
    kinds = {}
    for seed in range(40):
        candles = gen_walk(seed)
        for pos in build_positions(candles):
            total += 1
            new = exit_trade(dict(pos), candles, TAKER, SLIP)
            old = legacy_check_exit(dict(pos), candles)
            if new is not None:
                resolved += 1
                kinds[new[2]] = kinds.get(new[2], 0) + 1
            # compare with a float tolerance on net; exact on exit_t + kind
            if (new is None) != (old is None):
                mism += 1
            elif new is not None:
                if (abs(new[0] - old[0]) > 1e-12 or new[1] != old[1]
                        or new[2] != old[2]):
                    mism += 1
                    if mism <= 5:
                        print(f"  MISMATCH seed={seed} new={new} old={old} "
                              f"pos={pos}")

    print(f"  positions compared: {total}   resolved: {resolved}   "
          f"by kind: {kinds}")
    if resolved == 0:
        print("\nFAIL: test was vacuous — no position ever resolved.")
        return 1
    if mism:
        print(f"\nFAIL: {mism} position(s) diverged from legacy check_exit.")
        return 1
    print("\nPASS: core.exit_trade reproduces legacy check_exit "
          "trade-for-trade (sl / tp / tp_close / trailing / time).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
