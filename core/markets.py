"""Market model — the columns each market provides.

The capability rule drives everything:

    an indicator is available on a market iff
        set(indicator.inputs) <= market.provides

Consequences:
  - volume indicators (OBV, MFI, VWAP, VOL_RATIO) drop where there's no volume
    (FX spot)
  - candlestick patterns (need open/high/low) drop on prediction markets
    (which only have a probability `close`)
  - plain close-momentum (RSI, ROC, EMA) is available everywhere

The same check powers the Builder palette and strategy validation (no
per-indicator-per-market table).
"""
from dataclasses import dataclass

from .indicators import REGISTRY

OHLCV = frozenset({"open", "high", "low", "close", "volume"})
OHLC = frozenset({"open", "high", "low", "close"})


@dataclass(frozen=True)
class Market:
    id: str
    label: str
    provides: frozenset        # columns this market has
    series_kind: str           # "continuous" | "resolution"
    asset_class: str


MARKETS: dict = {}


def register_market(m: Market) -> Market:
    MARKETS[m.id] = m
    return m


register_market(Market("crypto_perp", "Crypto Perpetuals", OHLCV,
                       "continuous", "crypto_perp"))
register_market(Market("crypto_spot", "Crypto Spot", OHLCV,
                       "continuous", "crypto_spot"))
register_market(Market("equity", "Equities", OHLCV,
                       "continuous", "equity"))
register_market(Market("futures", "Futures", OHLCV,
                       "continuous", "futures"))
register_market(Market("fx_spot", "FX Spot", OHLC,          # no real volume
                       "continuous", "fx_spot"))
register_market(Market("prediction", "Prediction Markets",
                       frozenset({"close"}),                # close = prob
                       "resolution", "prediction"))


def available(indicator, market):
    """True if `market` provides every column `indicator` needs."""
    return set(indicator.inputs) <= set(market.provides)


def available_indicators(market_id):
    """Indicator ids computable on this market — the Builder palette."""
    m = MARKETS[market_id]
    return sorted(i for i, ind in REGISTRY.items() if available(ind, m))


def unavailable_indicators(market_id):
    """{id: missing_columns} — what's greyed out, and why."""
    m = MARKETS[market_id]
    return {i: sorted(set(ind.inputs) - set(m.provides))
            for i, ind in REGISTRY.items() if not available(ind, m)}
