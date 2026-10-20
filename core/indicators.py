"""Indicator registry.

Every indicator is a function (candles, **params) -> list[float|None] aligned
to `candles` by index (None during warmup or when the value is undefined).
Candles are plain dicts {t, o, h, l, c, v} — the shape the data layer already
produces.

Three families live here:
  - raw columns (open/high/low/close/volume)
  - the custom indicators needed to express the founder's rules
    (ROC, VOL_RATIO, WICK_FRAC) — the ones that were hand-baked into
    paper_fleet.signal()/signal_capit()
  - a representative standard set (SMA, EMA, RSI, ATR) to prove the
    standard-indicator path plugs into the same interface

The full TA-Lib set drops in behind this exact interface — each wrapper is
just another register(Indicator(...)). Nothing else in the stack changes.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Indicator:
    id: str
    fn: Callable                 # (candles, **params) -> list[float|None]
    lookback: Callable           # (params: dict) -> int bars consumed
    label: str = ""
    category: str = ""
    inputs: tuple = ()
    params: tuple = ()           # ((name, type, default, min, max), ...)


REGISTRY: dict = {}


def register(ind: Indicator) -> Indicator:
    if ind.id in REGISTRY:
        raise ValueError(f"duplicate indicator id {ind.id!r}")
    REGISTRY[ind.id] = ind
    return ind


# --- raw columns ----------------------------------------------------------
def _col(key):
    def fn(candles):
        return [c[key] for c in candles]
    return fn


for _id, _k, _lbl in (("open", "o", "Open"), ("high", "h", "High"),
                      ("low", "l", "Low"), ("close", "c", "Close"),
                      ("volume", "v", "Volume")):
    # inputs use the column name (not the candle key) so the market
    # capability check speaks one vocabulary: {open,high,low,close,volume}
    register(Indicator(_id, _col(_k), lambda p: 0, label=_lbl,
                       category="price", inputs=(_id,)))


# --- custom indicators (express the founder's rules) ----------------------
def _roc(candles, period=16):
    """Rate of change over `period` bars: c[i]/c[i-period] - 1. This is the
    founder's 'runup' (period 16 = 4h) and 'drawdown' (period 96 = 24h)."""
    c = [x["c"] for x in candles]
    out = [None] * len(c)
    for i in range(period, len(c)):
        base = c[i - period]
        out[i] = (c[i] / base - 1) if base else None
    return out


register(Indicator("ROC", _roc, lambda p: p.get("period", 16),
                   label="Rate of Change", category="momentum",
                   inputs=("close",), params=(("period", int, 16, 1, 1000),)))


def _vol_ratio(candles, period=8):
    """Volume vs the mean of the prior `period` bars. Invalid (None) if any
    volume in [i-period, i] is <= 0 — mirrors the legacy alive-guard window
    k[i-8:i+1], so a zero-volume bar kills the signal exactly as before."""
    v = [x["v"] for x in candles]
    out = [None] * len(v)
    for i in range(period, len(v)):
        if any(x <= 0 for x in v[i - period:i + 1]):
            continue
        mu = sum(v[i - period:i]) / period      # prior `period` bars
        if mu <= 0:
            continue
        out[i] = v[i] / mu
    return out


register(Indicator("VOL_RATIO", _vol_ratio, lambda p: p.get("period", 8),
                   label="Volume Ratio", category="volume",
                   inputs=("volume",), params=(("period", int, 8, 1, 500),)))


def _wick_frac(candles, period=16):
    """Upper-wick share of the synthetic `period`-bar range: open taken from
    the first bar of the window, high/low across the window. Mirrors the
    legacy wick filter (period 16 = 4h)."""
    out = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        seg = candles[i - period + 1:i + 1]
        O = seg[0]["o"]
        Hh = max(x["h"] for x in seg)
        Ll = min(x["l"] for x in seg)
        rng = Hh - Ll
        if rng <= 0:
            continue
        out[i] = (Hh - max(O, candles[i]["c"])) / rng
    return out


register(Indicator("WICK_FRAC", _wick_frac, lambda p: p.get("period", 16) - 1,
                   label="Upper Wick Fraction", category="geometry",
                   inputs=("open", "high", "low", "close"),
                   params=(("period", int, 16, 2, 500),)))


# --- standard set -----------------------------------------------------------
# The full standard library (SMA, EMA, RSI, ATR, MACD, Bollinger, Stochastic,
# ADX, candlestick patterns, …) is registered from TA-Lib's own metadata by
# core/talib_wrap.py, which core/__init__.py imports on load. Those are the
# canonical reference implementations — we do not hand-roll them.
