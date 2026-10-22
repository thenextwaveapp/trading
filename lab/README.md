# lab/

The founder's research — proof-of-process, not the product. Nothing in here
ships or runs in production. This is where strategies were discovered,
backtested, and argued with before any of it became a bot.

## Contents

- `research/` — all analysis/backtest/fetch scripts (and `research/_archive/`, the dial graveyard)
- `reports/` — analysis output, timestamped
- `backtest/` — candle caches + ledgers
- `master/` — consolidated trades master, feature matrix, labels
- `bn/` — Binance/HL data pullers
- `Invo/` — raw scrapes: users, portfolios, trades
- `weather.py` — market-weather almanac builder (reads `backtest/`, imports from `research/`)

## Running

Lab scripts read their data relative to this directory and import the product
from the repo root. Run them from `lab/`:

```
cd lab && python3 research/<script>.py
```

The scripts that need the product on the path bootstrap it themselves
(`from core import regime`, `from runtime.paper_fleet import …`); the rest read
their datasets relative to `lab/` (`backtest/…`, `master/…`, `reports/…`).
