"""Strategy evaluator — shared by both backtest and live.

entry_signal() answers "does this strategy fire on bar i?" by applying two
validity guards (gapless tape over the strategy's lookback, and a market-alive
check) and then the strategy's entry conditions. A `fresh` strategy fires only
on the bar its entry becomes newly true.

Guards: gapless over the lookback window, nonzero volume over the recent
window, a non-flat current bar, and optional UTC hour/day signal windows.
"""
from bisect import bisect_right
from datetime import datetime, timezone

from .expr import eval_node

M15 = 900_000
ALIVE_VOL_BARS = 8        # volume guard window k[i-8:i+1]


def align_series(base, base_ms, aux, aux_ms):
    """Map each base bar to the aux bar most recently CLOSED at or before the
    base bar's close — the causal, no-lookahead alignment for a cross-series
    (multi-timeframe / cross-asset) operand. Returns a list the length of
    `base`; entry -1 means no aux bar had closed yet. An aux bar k closes at
    aux[k]["t"] + aux_ms; we want the largest k whose close <= base bar close."""
    aux_close = [c["t"] + aux_ms for c in aux]
    return [bisect_right(aux_close, c["t"] + base_ms) - 1 for c in base]


def build_aux(base, base_ms, series_by_key):
    """Build the `aux` dict the evaluator reads from raw cross-series data.
    `series_by_key` maps (symbol, tf) -> (candles, interval_ms). Each entry gets
    a precomputed causal alignment against the base tape."""
    return {key: {"candles": c,
                  "align": align_series(base, base_ms, c, ms)}
            for key, (c, ms) in series_by_key.items()}


def _index_ok(candles, i, L):
    return i - L >= 0 and i - ALIVE_VOL_BARS >= 0


def _bar_ms(strategy):
    return int(strategy.get("_interval_ms") or M15)


def _gapless(candles, i, L, step, market=None):
    if market in ("equity", "futures", "fx_spot"):
        return candles[i]["t"] > candles[i - L]["t"] if L > 0 else True
    return candles[i]["t"] - candles[i - L]["t"] == L * step


def _alive(candles, i):
    if candles[i]["h"] == candles[i]["l"]:
        return False
    return all(candles[j]["v"] > 0
               for j in range(i - ALIVE_VOL_BARS, i + 1))


def _timing_ok(strategy, candles, j):
    hours = strategy.get("_timing_hours") or ()
    days = strategy.get("_timing_days") or ()
    dates = strategy.get("_timing_dates") or ()
    if not hours and not days and not dates:
        return True
    close_t = candles[j]["t"] + _bar_ms(strategy)
    dt = datetime.fromtimestamp(close_t / 1000, tz=timezone.utc)
    if hours and dt.hour not in hours:
        return False
    if days and dt.weekday() not in days:
        return False
    if dates:
        o = dt.date().toordinal()
        if not any(a <= o <= b for a, b in dates):
            return False
    return True


def _book_entry_true(strategy, book, candles, j, cache, aux):
    """Does this book's entry tree pass every guard and fire at bar j?"""
    L = book["_lookback"]
    if not _index_ok(candles, j, L):
        return False
    if not _gapless(candles, j, L, _bar_ms(strategy), strategy.get("market")):
        return False
    if not _alive(candles, j):
        return False
    if not _timing_ok(strategy, candles, j):
        return False
    return eval_node(candles, book["entry"], j, cache, aux)


def _book_fires(strategy, book, candles, i, cache, aux):
    """A book fires at i if its entry is true there and — when `fresh` — was not
    already true on the prior bar."""
    if not _book_entry_true(strategy, book, candles, i, cache, aux):
        return False
    if strategy.get("fresh") \
            and _book_entry_true(strategy, book, candles, i - 1, cache, aux):
        return False
    return True


def entry_signal(strategy, candles, i, cache=None, aux=None):
    """Return a signal dict if exactly one book fires on bar i, else None.

    A single-side bot has one book. A two-sided bot evaluates both; if both fire
    on the same bar the direction is ambiguous, so the bar is skipped — the
    engine never silently picks a side. The signal carries the firing book's
    direction (`dir`) and the book itself (`_book`) so build_position uses that
    book's exit rule.

    cache: optional dict reused across bars (indicator series are causal, so
    the same cache is valid for every i over one candle list).
    aux: optional cross-series data (build_aux) for operands that read another
    timeframe/instrument; None means base-series only."""
    cache = {} if cache is None else cache
    fired = [b for b in strategy["_books"]
             if _book_fires(strategy, b, candles, i, cache, aux)]
    if len(fired) != 1:
        return None
    book = fired[0]
    return {"t_sig": candles[i]["t"] + _bar_ms(strategy),
            "entry": candles[i]["c"],
            "i": i,
            "side": book["side"],
            "dir": book["dir"],
            "_book": book}
