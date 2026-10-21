"""Momo parity — the composable momo spec reproduces paper_fleet.signal_momo()
bar-for-bar (fire/no-fire, t_sig, entry) AND the new `sig` stop mode reproduces
its signal-window stop. Legacy signal_momo is vendored verbatim (paper_fleet.py
lines 409-436, MOMO_VOL=2.5) so the test pins it with no heavy import.

Run:  python3 -m core.selftest_momo
"""
import math
import random
import sys

from core import parse, entry_signal
from core.backtest import build_position
from core.presets import MOMO

M15 = 900_000
MOMO_VOL = 2.5


# --- vendored legacy momo (verbatim from paper_fleet.signal_momo) ---------
def legacy_signal_momo(k):
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < 0.12:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < MOMO_VOL:
        return None
    O = k[i - 15]["o"]
    Hh = max(x["h"] for x in k[i - 15:i + 1])
    Ll = min(x["l"] for x in k[i - 15:i + 1])
    C = k[i]["c"]
    rng = Hh - Ll
    if rng <= 0:
        return None
    if (Hh - max(O, C)) / rng > 0.15 or (C - Ll) / rng < 0.80:
        return None
    stop = max(Ll, (O + C) / 2) * 0.999
    return dict(t_sig=k[i]["t"] + M15, entry=C, stop=stop, runup=runup)


# --- candle generators ----------------------------------------------------
def gen_random(seed, n=500):
    r = random.Random(seed)
    t0, out, px = 1_600_000_000_000, [], 100.0
    for i in range(n):
        drift = r.gauss(0, 0.04)
        if r.random() < 0.08:
            drift += 0.18                      # clean pump -> incidental momo
        o = px
        px = max(px * math.exp(drift), 1e-6)
        cl = px
        hi = max(o, cl) * (1 + abs(r.gauss(0, 0.015)))
        lo = min(o, cl) * (1 - abs(r.gauss(0, 0.015)))
        v = max(r.lognormvariate(10, 0.6), 1.0)
        if r.random() < 0.12:
            v *= 3
        out.append(dict(t=t0 + i * M15, o=o, h=hi, l=lo, c=cl, v=v))
    return out


def _ramp(extra_last):
    """25 flat bars, a 16-bar +1%/bar ramp, then a final bar built by
    `extra_last(o, px)` — lets each scenario shape only the firing bar."""
    t0, out, px = 1_600_000_000_000, [], 100.0
    for i in range(25):
        out.append(dict(t=t0 + i * M15, o=px, h=px * 1.001, l=px * 0.999,
                        c=px, v=1000.0))
    for i in range(25, 41):
        o = px
        px *= 1.01
        out.append(dict(t=t0 + i * M15, o=o, h=px * 1.001, l=o * 0.999,
                        c=px, v=1000.0))
    out.append(extra_last(t0 + 41 * M15, px))
    return out


def craft_fire(t, px):                    # strong green close, high vol, low wick
    c = px * 1.05
    return dict(t=t, o=px, h=c * 1.001, l=px * 0.999, c=c, v=5000.0)


def craft_bigwick(t, px):                 # same up-move but a tall upper wick
    c = px * 1.05
    return dict(t=t, o=px, h=c * 1.30, l=px * 0.999, c=c, v=5000.0)


def craft_midclose(t, px):                # closes mid-range (not top 20%)
    hi = px * 1.10
    return dict(t=t, o=px, h=hi, l=px * 0.95, c=px * 1.02, v=5000.0)


def craft_lowvol(t, px):                  # clean breakout but no volume
    c = px * 1.05
    return dict(t=t, o=px, h=c * 1.001, l=px * 0.999, c=c, v=1000.0)


# --- comparison -----------------------------------------------------------
def compare(label, strat, candles):
    start = strat["_lookback"] + 8
    cache, mism, fires = {}, [], 0
    for i in range(start, len(candles)):
        new = entry_signal(strat, candles, i, cache)
        old = legacy_signal_momo(candles[:i + 1])
        nf, of = new is not None, old is not None
        fires += of
        if nf != of:
            mism.append((i, "fire", nf, of))
        elif nf:
            if new["t_sig"] != old["t_sig"] or new["entry"] != old["entry"]:
                mism.append((i, "sig", new, old))
            stop = build_position(strat, candles, i, new)["stop"]
            if abs(stop - old["stop"]) > 1e-9:
                mism.append((i, "stop", stop, old["stop"]))
    return label, len(candles) - start, fires, mism


def main():
    strat = parse(MOMO)
    jobs = [compare(f"random#{s}", strat, gen_random(s)) for s in range(12)]
    jobs.append(compare("craft fire", strat, _ramp(craft_fire)))
    jobs.append(compare("craft bigwick", strat, _ramp(craft_bigwick)))
    jobs.append(compare("craft midclose", strat, _ramp(craft_midclose)))
    jobs.append(compare("craft lowvol", strat, _ramp(craft_lowvol)))

    fires = sum(j[2] for j in jobs)
    bad = [j for j in jobs if j[3]]
    for label, bars, fo, mism in jobs:
        print(f"  [{'OK ' if not mism else 'FAIL'}] {label:16s} bars={bars:4d} "
              f"fires={fo}" + (f"  MISMATCH={mism[:3]}" if mism else ""))
    print(f"\n  total legacy fires: {fires}")
    if fires == 0:
        print("\nFAIL: vacuous — legacy momo never fired.")
        return 1
    if bad:
        print(f"\nFAIL: {len(bad)} scenario(s) diverged.")
        return 1
    print("\nPASS: momo spec reproduces signal_momo() entry + sig-stop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
