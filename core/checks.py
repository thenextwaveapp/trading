"""Robustness checks — the honesty battery a strategy passes before you trust
it. Generalizes the research's own tests (pump_short_robustness.py): does the
edge survive higher costs, survive a late fill, and beat random entries?

Each check returns {key, label, passed, stat, threshold, detail}. These are
instruments, not gates — the product shows them and lets you decide; it never
blocks you (DESIGN.md). A final `summary` reports how many passed.

run_checks(strategy, candles_by_ticker) -> {checks: [...], passed, total}
"""
import random as _random

from .backtest import (DEFAULTS, backtest_universe, build_position,
                       exit_trade)
from .evaluator import M15


def _net_per_trade(res):
    return res["stats"]["net_pct_per_trade"]


def _cost_stress(strategy, uni, base_npt, mult=3.0):
    cfg = {**DEFAULTS, "taker": DEFAULTS["taker"] * mult,
           "slip": DEFAULTS["slip"] * mult}
    npt = _net_per_trade(backtest_universe(strategy, uni, cfg))
    return {"key": "cost_stress",
            "label": f"Survives {mult:g}x trading costs",
            "passed": npt > 0, "stat": round(npt, 4), "threshold": 0.0,
            "detail": {"base_net_per_trade": round(base_npt, 4),
                       "stressed_net_per_trade": round(npt, 4)}}


def _entry_delay(strategy, uni, base_npt, bars=1):
    npt = _net_per_trade(backtest_universe(strategy, uni, entry_delay=bars))
    kept = (npt / base_npt) if base_npt else 0.0
    return {"key": "entry_delay",
            "label": f"Survives a {bars*15}-min late fill",
            "passed": npt > 0, "stat": round(npt, 4), "threshold": 0.0,
            "detail": {"base_net_per_trade": round(base_npt, 4),
                       "delayed_net_per_trade": round(npt, 4),
                       "edge_kept": round(kept, 3)}}


def _placebo(strategy, uni, real_trades, rounds=100, seed=7):
    n = len(real_trades)
    if n == 0:
        return {"key": "placebo", "label": "Beats random entries",
                "passed": False, "stat": 0.0, "threshold": 0.0,
                "detail": {"reason": "no real trades"}}
    rnd = _random.Random(seed)
    L = strategy["_lookback"]
    pool = [(tk, i) for tk, c in uni.items()
            for i in range(L + 8, len(c) - 1)]
    if len(pool) < n:
        return {"key": "placebo", "label": "Beats random entries",
                "passed": False, "stat": 0.0, "threshold": 0.0,
                "detail": {"reason": "universe too small for placebo"}}
    taker, slip = DEFAULTS["taker"], DEFAULTS["slip"]
    means = []
    for _ in range(rounds):
        nets = []
        for tk, i in rnd.sample(pool, n):
            c = uni[tk]
            fake = {"entry": c[i]["c"], "t_sig": c[i]["t"] + M15, "i": i}
            ex = exit_trade(build_position(strategy, c, i, fake), c,
                            taker, slip)
            if ex:
                nets.append(ex[0])
        if nets:
            means.append(sum(nets) / len(nets) * 100)
    means.sort()
    p95 = means[min(len(means) - 1, int(0.95 * len(means)))] if means else 0.0
    real = sum(t["net"] for t in real_trades) / n * 100
    return {"key": "placebo", "label": "Beats random entries",
            "passed": real > p95, "stat": round(real, 4),
            "threshold": round(p95, 4),
            "detail": {"real_net_per_trade": round(real, 4),
                       "placebo_p95": round(p95, 4), "rounds": len(means)}}


def run_checks(strategy, candles_by_ticker):
    """Run the battery. `candles_by_ticker` = {ticker: [candles]}."""
    base = backtest_universe(strategy, candles_by_ticker)
    base_npt = _net_per_trade(base)
    checks = [
        _cost_stress(strategy, candles_by_ticker, base_npt),
        _entry_delay(strategy, candles_by_ticker, base_npt),
        _placebo(strategy, candles_by_ticker, base["trades"]),
    ]
    passed = sum(1 for c in checks if c["passed"])
    return {"checks": checks, "passed": passed, "total": len(checks),
            "base_net_per_trade": round(base_npt, 4),
            "base_trades": base["stats"]["n"]}
