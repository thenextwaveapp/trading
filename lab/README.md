# lab/

The founder's research — proof-of-process, not the product. Nothing in here
ships or runs in production. This is where strategies were discovered,
backtested, and argued with before any of it became a bot.

Contents move in here as the product is untangled from the repo root. The
research scripts (`research/`) and their datasets (`reports/`, `backtest/`,
`master/`) are coupled to the product's flat root modules (`import regime`,
`open("fleet_config.json")`) and can only move once the product has a proper
package home — until then they stay at root.

- `Invo/` — raw scrapes: users, portfolios, trades (research input data)
