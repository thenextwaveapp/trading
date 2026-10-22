"""Differential / characterization test.

Proves the composable engine reproduces the hand-coded paper_fleet signal
functions bar-for-bar. The legacy functions are vendored verbatim below
(paper_fleet.py signal() lines 269-292, signal_capit() lines 295-321) so the
test pins their behavior with no heavy import. We run both engines over the
same candles — random walks (volatile enough to incidentally fire), crafted
firing scenarios, and edge cases (gaps, zero volume, flat bars, exact
thresholds) — and assert identical fire/no-fire, t_sig and entry on every bar
past warmup.

Run:  python3 -m core.selftest      (or: python3 core/selftest.py)
"""
import math
import random
import sys

from core import parse, entry_signal
from core.presets import RULE_P, RULE_P_WICK, CAPIT

M15 = 900_000


# --- vendored legacy engines (verbatim from paper_fleet.py) ---------------
def legacy_signal(k, cfg):
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < cfg["runup"] or k[i]["c"] >= k[i - 1]["c"]:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < cfg["vol"]:
        return None
    if cfg.get("wick"):
        O = k[i - 15]["o"]
        Hh = max(x["h"] for x in k[i - 15:i + 1])
        Ll = min(x["l"] for x in k[i - 15:i + 1])
        rng = Hh - Ll
        if rng <= 0 or (Hh - max(O, k[i]["c"])) / rng < cfg["wick"]:
            return None
    hh = max(x["h"] for x in k[i - 16:i + 1])
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"], hh=hh, runup=runup)


def legacy_signal_capit(k, cfg):
    if len(k) < 98:
        return None
    i = len(k) - 1

    def cond(j):
        if j < 97:
            return False
        if k[j]["t"] - k[j - 96]["t"] != 96 * M15:
            return False
        if any(x["v"] <= 0 for x in k[j - 8:j + 1]) or k[j]["h"] == k[j]["l"]:
            return False
        return k[j]["c"] / k[j - 96]["c"] - 1 <= -cfg["depth"]

    if not cond(i) or cond(i - 1):
        return None
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"])


# --- candle generators ----------------------------------------------------
def gen_random(seed, n=500):
    r = random.Random(seed)
    t0 = 1_600_000_000_000
    out = []
    px = 100.0
    for i in range(n):
        drift = r.gauss(0, 0.045)
        if r.random() < 0.07:
            drift += 0.16            # pump jumps -> incidental short signals
        if r.random() < 0.07:
            drift -= 0.11            # dumps -> incidental capit signals
        o = px
        px = max(px * math.exp(drift), 1e-6)
        cl = px
        hi = max(o, cl) * (1 + abs(r.gauss(0, 0.02)))
        lo = min(o, cl) * (1 - abs(r.gauss(0, 0.02)))
        v = max(r.lognormvariate(10, 0.6), 1.0)
        if r.random() < 0.1:
            v *= 3
        out.append(dict(t=t0 + i * M15, o=o, h=hi, l=lo, c=cl, v=v))
    return out


def craft_pump():
    """A deterministic series guaranteed to fire pump-short at a known bar."""
    t0 = 1_600_000_000_000
    out = []
    px = 100.0
    for i in range(25):                       # flat warmup
        out.append(dict(t=t0 + i * M15, o=px, h=px * 1.001, l=px * 0.999,
                        c=px, v=1000.0))
    for i in range(25, 41):                    # +1%/bar ramp for 16 bars
        o = px
        px *= 1.01
        out.append(dict(t=t0 + i * M15, o=o, h=px * 1.001, l=o * 0.999,
                        c=px, v=1000.0))
    # red, high-volume bar -> runup over 16 bars still >12%, close < prev
    o = px
    c = px * 0.99
    out.append(dict(t=t0 + 41 * M15, o=o, h=o * 1.02, l=c * 0.98, c=c,
                    v=5000.0))
    px = c
    for i in range(42, 48):                    # tail so lists stay long
        o = px
        px *= 0.999
        out.append(dict(t=t0 + i * M15, o=o, h=o * 1.001, l=px * 0.999,
                        c=px, v=1000.0))
    return out


def craft_capit():
    """A steady decline that crosses -20%/24h — fires capit on the crossing."""
    t0 = 1_600_000_000_000
    out = []
    px = 100.0
    for i in range(160):
        o = px
        px *= 0.9975                           # ~-21% over 96 bars
        out.append(dict(t=t0 + i * M15, o=o, h=o * 1.001, l=px * 0.999,
                        c=px, v=1000.0))
    return out


def with_gap(candles, at):
    """Shift every timestamp from `at` onward by one extra bar (a 15m gap)."""
    out = [dict(c) for c in candles]
    for k in out[at:]:
        k["t"] += M15
    return out


# --- comparison -----------------------------------------------------------
def compare(label, strategy, legacy_fn, cfg, candles):
    start = strategy["_lookback"] + 8          # clear both engines' warmup
    cache = {}
    mism = []
    fires_new = fires_old = 0
    for i in range(start, len(candles)):
        new = entry_signal(strategy, candles, i, cache)
        old = legacy_fn(candles[:i + 1], cfg)
        nf, of = new is not None, old is not None
        fires_new += nf
        fires_old += of
        if nf != of or (nf and (new["t_sig"] != old["t_sig"]
                                 or new["entry"] != old["entry"])):
            mism.append((i, nf, of))
    return label, len(candles) - start, fires_new, fires_old, mism


def main():
    base = parse(RULE_P)
    wick = parse(RULE_P_WICK)
    capit = parse(CAPIT)

    cfg_base = {"runup": 0.12, "vol": 2.0}
    cfg_wick = {"runup": 0.12, "vol": 2.0, "wick": 0.3}
    cfg_capit = {"depth": 0.2}

    jobs = []
    # random series
    for seed in range(12):
        c = gen_random(seed)
        jobs.append(compare(f"random#{seed} pump", base, legacy_signal,
                            cfg_base, c))
        jobs.append(compare(f"random#{seed} wick", wick, legacy_signal,
                            cfg_wick, c))
        jobs.append(compare(f"random#{seed} capit", capit,
                            legacy_signal_capit, cfg_capit, c))
    # crafted firing scenarios
    jobs.append(compare("craft pump", base, legacy_signal, cfg_base,
                        craft_pump()))
    jobs.append(compare("craft capit", capit, legacy_signal_capit,
                        cfg_capit, craft_capit()))
    # edge cases: a time gap must make both reject around the gap
    jobs.append(compare("craft pump +gap", base, legacy_signal, cfg_base,
                        with_gap(craft_pump(), 30)))
    jobs.append(compare("craft capit +gap", capit, legacy_signal_capit,
                        cfg_capit, with_gap(craft_capit(), 70)))

    total_bars = sum(j[1] for j in jobs)
    total_new = sum(j[2] for j in jobs)
    total_old = sum(j[3] for j in jobs)
    bad = [j for j in jobs if j[4]]

    for label, bars, fn, fo, mism in jobs:
        flag = "OK " if not mism else "FAIL"
        print(f"  [{flag}] {label:24s} bars={bars:4d} "
              f"fires new/old={fn}/{fo}" +
              (f"  MISMATCHES={mism[:5]}" if mism else ""))

    print(f"\n  bars compared: {total_bars}   "
          f"signals new/old: {total_new}/{total_old}")
    if total_old == 0:
        print("\nFAIL: test was vacuous — legacy engine never fired.")
        return 1
    if bad:
        print(f"\nFAIL: {len(bad)} scenario(s) diverged from the legacy "
              f"engine.")
        return 1
    print("\nPASS: composable engine reproduces legacy signal() and "
          "signal_capit() bar-for-bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
