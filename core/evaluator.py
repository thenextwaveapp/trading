"""Strategy evaluator — shared by both backtest and live.

entry_signal() answers "does this strategy fire on bar i?" by applying two
validity guards (gapless tape over the strategy's lookback, and a market-alive
check) and then the strategy's entry conditions. A `fresh` strategy fires only
on the bar its entry becomes newly true.

Guards: gapless over the lookback window, nonzero volume over the recent
window, and a non-flat current bar.
"""
from .expr import eval_node

M15 = 900_000
ALIVE_VOL_BARS = 8        # volume guard window k[i-8:i+1]


def _index_ok(candles, i, L):
    return i - L >= 0 and i - ALIVE_VOL_BARS >= 0


def _gapless(candles, i, L):
    return candles[i]["t"] - candles[i - L]["t"] == L * M15


def _alive(candles, i):
    if candles[i]["h"] == candles[i]["l"]:
        return False
    return all(candles[j]["v"] > 0
               for j in range(i - ALIVE_VOL_BARS, i + 1))


def _entry_true(strategy, candles, j, cache):
    L = strategy["_lookback"]
    if not _index_ok(candles, j, L):
        return False
    if not _gapless(candles, j, L):
        return False
    if not _alive(candles, j):
        return False
    return eval_node(candles, strategy["entry"], j, cache)


def entry_signal(strategy, candles, i, cache=None):
    """Return a signal dict if `strategy` fires on bar i, else None.

    cache: optional dict reused across bars (indicator series are causal, so
    the same cache is valid for every i over one candle list)."""
    cache = {} if cache is None else cache
    if not _entry_true(strategy, candles, i, cache):
        return None
    if strategy.get("fresh") and _entry_true(strategy, candles, i - 1, cache):
        return None
    return {"t_sig": candles[i]["t"] + M15,
            "entry": candles[i]["c"],
            "i": i,
            "side": strategy["side"]}
