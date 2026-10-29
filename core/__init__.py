"""core — the composable strategy engine.

indicators -> conditions -> strategy -> signals. Pure, deterministic, no I/O.
Backtest and live fleet share the same evaluator.
"""
from .strategy import parse, StrategyError
from .evaluator import entry_signal, M15
from .indicators import REGISTRY, Indicator
from .markets import (MARKETS, Market, available, available_indicators,
                      unavailable_indicators)
from . import indicators_std       # pure-Python standard set, dependency-free (wins)
from . import talib_wrap           # registers the remaining TA-Lib set on import

__all__ = ["parse", "StrategyError", "entry_signal", "M15",
           "REGISTRY", "Indicator", "MARKETS", "Market", "available",
           "available_indicators", "unavailable_indicators", "talib_wrap"]
