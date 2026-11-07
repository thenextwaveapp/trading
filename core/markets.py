"""Market model — the columns each market provides.

The capability rule drives everything:

    an indicator is available on a market iff
        set(indicator.inputs) <= (market.provides | market.feeds)

`provides` is the columns physically on the candle (open/high/low/close/volume)
— an indicator fn reads them straight off the bar. `feeds` is externally-sourced
inputs (social/news scores) that arrive via the aux path, NOT off the candle;
they are kept distinct so `provides` retains its one precise meaning while feed
inputs still gate the palette and validation through the same subset check.

Consequences:
  - volume indicators (OBV, MFI, VWAP, VOL_RATIO) drop where there's no volume
    (FX spot)
  - candlestick patterns (need open/high/low) drop on prediction markets
    (which only have a probability `close`)
  - plain close-momentum (RSI, ROC, EMA) is available everywhere
  - feed inputs (social/news) are available only where a feed is wired

The same check powers the Builder palette and strategy validation (no
per-indicator-per-market table).
"""
from dataclasses import dataclass

from .indicators import REGISTRY

OHLCV = frozenset({"open", "high", "low", "close", "volume"})
OHLC = frozenset({"open", "high", "low", "close"})


@dataclass(frozen=True)
class CostModel:
    """Per-side trading cost as a fraction of notional. A round trip costs
    `2*taker + slip` (the fee the backtest and live engines both apply), so this
    is where a market's microstructure — crypto taker, equity commission+spread,
    fx spread — stops being hardcoded crypto."""
    taker: float
    slip: float


@dataclass(frozen=True)
class Market:
    id: str
    label: str
    provides: frozenset        # columns this market has
    series_kind: str           # "continuous" | "resolution"
    asset_class: str
    cost: CostModel            # the market's trading-cost model
    regime_benchmark: str | None  # ticker whose trend x vol defines Weather;
    #                                None = this market has no regime gate
    feeds: frozenset = frozenset()  # externally-sourced inputs (social/news)
    #                                 available via the aux path, not the candle

    @property
    def has_volume(self) -> bool:
        return "volume" in self.provides


MARKETS: dict = {}


def register_market(m: Market) -> Market:
    MARKETS[m.id] = m
    return m


# Cost models are market-appropriate defaults (tunable), not guesses pinned to
# Binance perp fees. regime_benchmark is the series Weather measures trend/vol on.
CRYPTO_FEEDS = frozenset({"social", "news"})
EQUITY_FEEDS = frozenset({"social", "news"})

register_market(Market("crypto_perp", "Crypto Perpetuals", OHLCV,
                       "continuous", "crypto_perp",
                       CostModel(0.00045, 0.0005), "BTC", feeds=CRYPTO_FEEDS))
register_market(Market("crypto_spot", "Crypto Spot", OHLCV,
                       "continuous", "crypto_spot",
                       CostModel(0.001, 0.0005), "BTC", feeds=CRYPTO_FEEDS))
register_market(Market("equity", "Equities", OHLCV,
                       "continuous", "equity",
                       CostModel(0.0001, 0.0005), "SPY", feeds=EQUITY_FEEDS))
register_market(Market("futures", "Futures", OHLCV,
                       "continuous", "futures",
                       CostModel(0.00002, 0.0003), "SPY"))
register_market(Market("fx_spot", "FX Spot", OHLC,          # no real volume
                       "continuous", "fx_spot",
                       CostModel(0.0, 0.0001), None))
register_market(Market("prediction", "Prediction Markets",
                       frozenset({"close"}),                # close = implied prob
                       "resolution", "prediction",
                       CostModel(0.0, 0.01), None))         # thin books -> spread


def is_resolution(market_id):
    """True if the market settles to an outcome (a prediction contract resolves
    to 0/1 at expiry) rather than trading as a continuous price series. The
    engine uses this to switch entry guards, sizing, and the exit path."""
    m = MARKETS.get(market_id or "")
    return bool(m and m.series_kind == "resolution")


def _market_inputs(market):
    return set(market.provides) | set(market.feeds)


def available(indicator, market):
    """True if `market` supplies every input `indicator` needs — whether off the
    candle (provides) or via a wired feed (feeds)."""
    return set(indicator.inputs) <= _market_inputs(market)


def available_indicators(market_id):
    """Indicator ids computable on this market — the Builder palette."""
    m = MARKETS[market_id]
    return sorted(i for i, ind in REGISTRY.items() if available(ind, m))


def unavailable_indicators(market_id):
    """{id: missing_columns} — what's greyed out, and why."""
    m = MARKETS[market_id]
    inputs = _market_inputs(m)
    return {i: sorted(set(ind.inputs) - inputs)
            for i, ind in REGISTRY.items() if not available(ind, m)}
