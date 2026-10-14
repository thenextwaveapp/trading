#!/usr/bin/env python3
"""Backfill gaps in the dashboard's marks.csv from trades + Binance history.

The 5-min mark sampler only records while the dashboard runs; offline
windows are holes. Marked equity is reconstructible: realized equity is a
step function of equity_after at each exit_t, unrealized is
notional*side*(px/entry-1) summed over trades open at t — the same math
as _marked_equities(), with 15m closes standing in for live prices.

Usage: python3 research/backfill_marks.py [fleet_dir]     # default paper/fleet
Fills only gaps > 15 min (and the span before the first mark, back to the
earliest trade). Writes marks.csv in place, backup at marks.csv.bak.
"""
import csv
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from paper_fleet import VARIANTS  # noqa: E402

M15 = 900_000
STEP = 300_000                      # sampler cadence
KEEP = 14 * 86_400_000
START_EQUITY = 10_000.0
COST = 0.0019                       # round-trip taker+slip, for side inference
DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "paper", "fleet")
UNI = json.load(open(os.path.join(ROOT, "paper", "universe60.json")))


def direction(cfg):
    if cfg.get("twosided") or cfg.get("engine") in ("super", "churn"):
        return 0                    # per-trade inference
    return 1 if cfg.get("engine") in ("momo", "capit", "loser") else -1


CANDLES = {}


def closes(tk, t0, t1):
    """15m closes for ticker over [t0, t1], cached, keyed by candle open."""
    sym = UNI.get(tk)
    if not sym:
        return {}
    have = CANDLES.setdefault(tk, {})
    t0 = t0 // M15 * M15
    if not all((t0 + i * M15) in have for i in range(int((t1 - t0) // M15) + 1)):
        t = t0
        while t <= t1:
            url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}"
                   f"&interval=15m&startTime={t}&endTime={t1}&limit=1000")
            rows = json.load(urllib.request.urlopen(url, timeout=30))
            if not rows:
                break
            for r in rows:
                have[r[0]] = float(r[4])
            t = rows[-1][0] + M15
    return have


def px_at(tk, t):
    """Close of the last candle fully closed at time t."""
    return CANDLES.get(tk, {}).get((t - M15) // M15 * M15)


def read_trades(name):
    p = os.path.join(DIR, f"trades_{name}.csv")
    if not os.path.exists(p):
        return []
    out = []
    for r in list(csv.reader(open(p)))[1:]:
        if not r or r[0] == "ticker":
            continue
        try:
            out.append(dict(tk=r[0], t_sig=int(float(r[1])), entry=float(r[2]),
                            exit_t=int(float(r[4])), net=float(r[6]),
                            pnl=float(r[7]), notional=float(r[8]),
                            eq_after=float(r[9])))
        except (ValueError, IndexError):
            continue
    return sorted(out, key=lambda x: x["exit_t"])


def infer_side(tr, fixed):
    if fixed:
        return fixed
    px = px_at(tr["tk"], tr["exit_t"])
    if not px or abs(px / tr["entry"] - 1) < 0.001:
        return 1
    return 1 if (tr["net"] + COST) * (px / tr["entry"] - 1) > 0 else -1


def main():
    now = int(time.time() * 1000)
    path = os.path.join(DIR, "marks.csv")
    marks = []
    if os.path.exists(path):
        for r in csv.reader(open(path)):
            try:
                marks.append([int(r[0]), r[1], float(r[2])])
            except (ValueError, IndexError):
                continue
    have = {}
    for t, name, eq in marks:
        have.setdefault(name, []).append(t)

    added = dropped = 0
    for name, cfg in VARIANTS.items():
        trades = read_trades(name)
        fixed = direction(cfg)
        # scrub failed-fetch spikes: a mark at realized-only level while a
        # position was open and reconstruction says unrealized was material
        eq_of = {t: eq for t, n, eq in marks if n == name}
        bad = set()
        for t, eq in eq_of.items():
            opens = [tr for tr in trades if tr["t_sig"] <= t < tr["exit_t"]]
            if not opens:
                continue
            realized = START_EQUITY
            for tr in trades:
                if tr["exit_t"] <= t:
                    realized = tr["eq_after"]
            if abs(eq - realized) > 1.0:
                continue
            unreal = 0.0
            for tr in opens:
                closes(tr["tk"], tr["t_sig"], min(tr["exit_t"] + M15, now))
                tr["side"] = infer_side(tr, fixed)
                px = px_at(tr["tk"], t)
                if px:
                    unreal += tr["notional"] * tr["side"] * (px / tr["entry"] - 1)
            if abs(unreal) > 50:
                bad.add(t)
        if bad:
            marks = [r for r in marks if not (r[1] == name and r[0] in bad)]
            have[name] = [t for t in have.get(name, []) if t not in bad]
            dropped += len(bad)
            print(f"{name}: dropped {len(bad)} zero-unreal spike mark(s)")
        ts = sorted(have.get(name, []))
        lo = max(now - KEEP, min([t["t_sig"] for t in trades], default=now))
        hi = ts[-1] if ts else now
        # gap spans: before first mark, and >15min holes between marks
        gaps, prev = [], lo
        for t in ts:
            if t - prev > 3 * STEP:
                gaps.append((prev, t))
            prev = t
        if not ts and trades:
            gaps.append((lo, now))
        if not gaps:
            continue
        # prefetch candles for trades overlapping any gap, infer sides
        for tr in trades:
            if any(tr["t_sig"] < g1 and tr["exit_t"] > g0 for g0, g1 in gaps):
                closes(tr["tk"], tr["t_sig"], min(tr["exit_t"] + M15, now))
                tr.setdefault("side", infer_side(tr, fixed))
        for g0, g1 in gaps:
            t = (g0 // STEP + 1) * STEP
            while t < g1:
                realized = START_EQUITY
                for tr in trades:
                    if tr["exit_t"] <= t:
                        realized = tr["eq_after"]
                unreal = 0.0
                for tr in trades:
                    if tr["t_sig"] <= t < tr["exit_t"]:
                        px = px_at(tr["tk"], t)
                        if px:
                            unreal += tr["notional"] * tr.get("side", fixed or 1) \
                                * (px / tr["entry"] - 1)
                marks.append([t, name, round(realized + unreal, 2)])
                added += 1
                t += STEP
        print(f"{name}: filled {len(gaps)} gap(s)")

    marks.sort(key=lambda r: (r[0], r[1]))
    if os.path.exists(path):
        os.replace(path, path + ".bak")
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(marks)
    print(f"added {added}, dropped {dropped} -> {path}")


if __name__ == "__main__":
    main()
