"""Disk-backed streaming universe == eager dict, number-for-number.

Guards core/service.DiskUniverse and the RNG-replay placebo. The engine used to
hold the whole universe's candle tapes in RAM at once (a 5m/2yr all-perps run is
gigabytes); now it streams one tape at a time off disk. This must be a perfectly
transparent swap — backtest, checks (incl. placebo) and weather produce identical
results whether the universe is an eager dict or a DiskUniverse. A separate
reference reimplements the OLD random-access placebo to prove the replay didn't
move the number.
"""
import random as _random

from core import parse
from core.backtest import DEFAULTS, backtest_universe, build_position, exit_trade
from core.checks import run_checks
from core.conditions import conditions_breakdown
from core.evaluator import M15
from core.service import DiskUniverse

SPEC = {
    "name": "t", "side": "short", "market": "crypto_perp", "universe": "x", "timeframe": "15m",
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "RSI", "params": {"timeperiod": 14}}, "op": "crosses_above", "right": 60}]},
    "exit": {"time_bars": 16, "stop": {"mode": "dstop", "param": 0.03}, "take_profit": 0.05},
    "sizing": {"risk": 0.0075, "notional_cap": 0.2, "weight": 1.0},
}


def _series(seed, n=2500):
    r = _random.Random(seed)
    px = 100.0
    out = []
    t = 0
    for _ in range(n):
        px *= 1 + r.uniform(-0.012, 0.0125)
        o = px
        c = px * (1 + r.uniform(-0.004, 0.004))
        h = max(o, c) * (1 + r.uniform(0, 0.006))
        l = min(o, c) * (1 - r.uniform(0, 0.006))
        out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": r.uniform(10, 100)})
        t += M15
    return out


def _old_placebo(strategy, uni, real_trades, rounds=100, seed=7, max_samples=5000):
    """Pre-refactor random-access placebo — reference for the replay version."""
    n = len(real_trades)
    rnd = _random.Random(seed)
    L = strategy["_lookback"]
    tickers, weights = [], []
    for tk, c in uni.items():
        cnt = len(c) - 1 - (L + 8)
        if cnt > 0:
            tickers.append(tk); weights.append(cnt)
    sample_n = min(n, max_samples)
    taker, slip = DEFAULTS["taker"], DEFAULTS["slip"]
    means = []
    for _ in range(rounds):
        nets = []
        for tk in rnd.choices(tickers, weights=weights, k=sample_n):
            c = uni[tk]
            i = rnd.randrange(L + 8, len(c) - 1)
            fake = {"entry": c[i]["c"], "t_sig": c[i]["t"] + strategy.get("_interval_ms", M15), "i": i}
            ex = exit_trade(build_position(strategy, c, i, fake), c, taker, slip)
            if ex:
                nets.append(ex[0])
        if nets:
            means.append(sum(nets) / len(nets) * 100)
    means.sort()
    p95 = means[min(len(means) - 1, int(0.95 * len(means)))] if means else 0.0
    real = sum(t["net"] for t in real_trades) / n * 100 if n else 0.0
    return round(real, 4), round(p95, 4)


def main() -> int:
    s = parse(dict(SPEC))
    eager = {"BTC": _series(1), "ETH": _series(2), "SOL": _series(3), "AVAX": _series(4)}
    du = DiskUniverse()
    for tk, c in eager.items():
        du.put(tk, c)

    fails = []
    try:
        be = backtest_universe(s, eager)
        bd = backtest_universe(s, du)
        if be["stats"] != bd["stats"] or be["trades"] != bd["trades"]:
            fails.append("backtest_universe differs eager vs disk")

        ce = run_checks(s, eager)
        cd = run_checks(s, du)
        if ce != cd:
            fails.append("run_checks differs eager vs disk")

        we = conditions_breakdown(be["trades"], eager, bar_ms=M15)
        wd = conditions_breakdown(bd["trades"], du, bar_ms=M15)
        if we != wd:
            fails.append("conditions_breakdown differs eager vs disk")

        # the replay placebo must equal the old random-access placebo
        base = backtest_universe(s, eager)
        new_pl = next(c for c in run_checks(s, eager, base=base)["checks"] if c["key"] == "placebo")
        old_real, old_p95 = _old_placebo(s, eager, base["trades"])
        if (new_pl["stat"], new_pl["threshold"]) != (old_real, old_p95):
            fails.append(f"placebo replay != old: new=({new_pl['stat']},{new_pl['threshold']}) old=({old_real},{old_p95})")
    finally:
        du.close()

    if fails:
        for f in fails:
            print("  FAIL:", f)
        return 1
    print(f"[stream_universe] eager==disk across backtest/checks/weather; placebo replay matches old "
          f"({be['stats']['n']} trades, {len(eager)} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
