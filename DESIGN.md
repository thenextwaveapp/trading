# DESIGN — the product

Updated: 2026-10-19. The reference we build against. For how the *current*
single-user research system works, see `README.md`; this describes what it
becomes.

## What we're building

A terminal for trading-strategy exploration. Anyone logs in and runs the
whole loop — build a strategy, backtest it, stress-check it, test it across
market regimes, deploy it to a live paper (or real) account, watch it, and
compare it against their other strategies — **entirely in the UI, never
touching code.**

We ship the **tooling, not the signals.** The edge stays private to each
user; the product is the machine that lets anyone do what the founder did.

### Three buckets (the mental model that resolves "what is what")

1. **System** — the running machine: data, indicators, backtest, execution.
   Ships, runs per user.
2. **Process** — the research pipeline itself. Ships, *inside* the product as
   the build→backtest→checks→weather→graduate flow.
3. **Lab** — the founder's past research: `research/`, `reports/`,
   `backtest/`, `Invo/`, `master/`, `bn/`. Proof the process works. Does NOT
   ship; archive out of the product repo. Good marketing, not product code.

## Principles

- **It's an instrument, not a gatekeeper.** The tool never tells you no. Its
  job is information and execution, never permission. The pipeline phases are
  readouts you can act on or ignore; Graduate is a deploy button, not a
  bouncer. You can ship a strategy that failed every check to live money —
  your capital, your call.
- **Full surface, built for the power user.** The founder is the first
  customer; the next customers are people like the founder. The value is how
  much there is to explore — never curate it down, never dumb it down.
- **Standard primitives, nothing undefined.** The foundation is the full
  TA-Lib indicator set as defined, industry-standard building blocks — not
  bespoke "engines," not the founder's biased research subset. A strategy is
  those indicators composed into conditions.
- **The asset class is a data/execution concern, never a strategy concern.**
  The core model is identical across crypto, stocks, and prediction markets.

## The one invariant that cannot bend

Because nothing in the builder ever blocks the user, **the instruments must
never lie.** Backtest and live run the *same* expression engine; the universe
is point-in-time; fees and slippage are always on; results are
survivorship-free; each market carries its own truthful fee/session/borrow/
resolution model. Users act on these numbers with real money and nothing else
stands in the way — the integrity of the readouts is the entire product.

(The founder's own research already caught this: a point-in-time universe
rebuild cut static-backtest results ~1000×. "Judge on honest,
survivorship-free numbers" is not a detail, it's the product.)

---

## 1. Core objects (the data model — everything hangs off this)

**Indicator** — a named, parameterized function over OHLCV returning a
series. Full TA-Lib set + a small custom set, all behind one interface.

```
Indicator { id, name, inputs: [open|high|low|close|volume],
            params: {period: 14, ...}, output: series }
```

Standard: RSI, MACD, EMA, SMA, ATR/NATR, Bollinger, Stochastic, ADX, VWAP,
OBV, … (~150 in TA-Lib). Custom (one-liners behind the same interface):
`ROC(16)` = run-up, `VOL_RATIO(8)`, `WICK_FRAC()`, `DRAWDOWN(96)`,
`BTC_REGIME()`, `HOUR_OF_DAY()`.

**Condition** — a boolean expression over indicators/constants.

```
Condition      { left: Indicator|const, op: < > <= >= == crosses_above
                 crosses_below, right: Indicator|const }
ConditionGroup { logic: AND|OR|NOT, children: [Condition|ConditionGroup] }
```

**Rule** — entry and exit.

```
EntryRule = ConditionGroup
ExitRule  { time_bars, stop: {mode, param}, take_profit, trailing,
            exit_conditions: ConditionGroup, hold_to_resolution }
```

Stop modes: `hh` (param = buffer above a reference high), `trail` (param =
k × NATR), `none`, `dstop` (param = fraction below entry), `sig`
(signal-computed), `ext` (session/1h extreme).

**Strategy** — replaces "engine + variant" entirely.

```
Strategy { id, name, side: long|short|both, market_id, universe,
           entry: EntryRule, exit: ExitRule,
           sizing: {risk, notional_cap, weight},
           filters: [regime|time|btc gates], parent_id }
```

**Fleet** — a set of strategies sharing one account.

```
Fleet { id, owner, market_scope,
        account: {start_equity, risk, notional_cap, max_conc, kill_dd,
                  kill_lookback, kill_pause, fees:{taker, slip}},
        strategies: [Strategy], alerts }
```

**Preset** — a saved, forkable Strategy. The old engines (pump_short, capit,
loser, momo, super, books) seed the preset gallery; nothing is special about
them anymore — each is just one composition.

**Market / Instrument** — the multi-asset spine (see §6).

```
Market     { id, asset_class: crypto_perp|crypto_spot|equity|option|
             prediction, venue, data_source, session_calendar, tick_size,
             lot_size, fee_model, shortable, settlement }
Instrument { symbol, market_id, metadata }   // metadata is asset-specific
```

`fleet_config.json` dies — strategies become rows. The config file was the
single-tenant version of the Strategy table.

## 2. The stack (layers, bottom to top)

1. **Data layer** — candle/series fetch + cache, per data source, normalized
   to the common series interface. Shared cache across users.
2. **Indicator library** — TA-Lib wrapped + custom, uniform
   `(series, params) → series`.
3. **Expression engine** — evaluates a ConditionGroup against a window →
   boolean. Used by BOTH backtest and live (the honesty invariant).
4. **Backtest engine** — replays history through the expression engine,
   applies entry/exit, computes trades/PnL with fees+slip, point-in-time
   universe, no survivorship.
5. **Checks engine** — cost stress, entry-delay ladder, placebo/random
   universe, out-of-sample split, leave-one-out.
6. **Weather engine** — regime dial + classification.
7. **Execution engine** — scan once, evaluate N strategies, manage positions,
   kill-switch; paper or live via an execution adapter.
8. **API + DB** — multi-tenant store (Supabase); a job queue for backtests.
9. **Web UI** — the React screens.

Provenance: layers 4–7 generalize the existing scripts — `backtest*.py` →
backtest engine, `robustness_backtest.py`/`pump_short_robustness.py` → checks,
`weather.py`/`regime.py` → weather, `paper_fleet.py` → execution.

## 3. The pipeline (how a user uses it — all instruments, no gates)

- **Build** — pick a market + universe, drag indicators into entry/exit
  conditions, set side, sizing, filters. Full palette, nothing hidden. Fork a
  preset or start blank. → a `Strategy`.
- **Backtest** — run over history. Trades, equity curve, net %/trade, win
  rate, drawdown. Honest numbers (PIT universe, fees on).
- **Checks** — robustness battery; pass/fail per test as information.
- **Weather** — replays across regimes; optionally attach a regime gate.
- **Graduate** — a deploy button. Adds the Strategy to a Fleet (paper or
  live). No approval gate.
- **Monitor** — live dashboard: positions marked to price, equity, trades,
  logs, alerts.
- **Compare** — leaderboard across the user's strategies: live vs backtest,
  each variant's verdict.

Core loop: clone a Strategy, change one condition/param, re-run. Forking and
sweeping must be cheap — that's the exploration surface.

## 4. Runtime / execution model

**One scanner per market → indicators computed once → N strategy
evaluations → fan out to owning Fleets.** Every cadence tick: fetch the
market's candles once, compute needed indicators once, run every active
Strategy's ConditionGroup through the shared expression engine; a signal goes
to whichever Fleet(s) own that Strategy; each Fleet manages its own
positions/equity/kill-switch. This is exactly what `paper_fleet.py` already
does for the founder's variants — **multi-tenant is just "the strategies
belong to different users."**

**Backtests are jobs** — heavy, so queued with workers, not inline. Results
cache keyed by (strategy-spec hash, date range, universe); identical specs
never recompute.

## 5. Storage / multi-tenancy

- **Auth** — Supabase Auth. Each user owns Fleets and Strategies.
- **Per-user rows** — Fleets, Strategies (full spec as structured JSON),
  paper accounts, positions, trade logs, backtest/check results.
- **Shared** — indicator library, candle cache, market scanners, preset
  gallery.

## 6. Multi-asset: crypto → stocks → predictions → "and so on"

The core (`indicators → conditions → strategy → fleet` + the whole pipeline)
is **identical across asset classes.** Expansion = swapping adapters below the
expression engine and adding a thin instrument model.

**Generalizes for free:** indicators (TA-Lib runs on any series), expression
engine, backtest/checks/weather engines, scan-once runtime, the entire UI.

**New abstraction layer:**
- **Market/Instrument model** (§1) — `Strategy.universe` is market-scoped;
  parallel scanners per market.
- **Data adapters** — one per source (Binance, an equities vendor,
  Polymarket/Kalshi), all normalizing to the common series interface.
- **Execution adapters** — one per venue (Hyperliquid, a stock broker,
  a prediction venue).
- **Asset-specific indicators/fields** — surfaced only where supported:
  perps (funding, open interest), equities (earnings, fundamentals,
  corporate actions, borrow cost), predictions (implied prob,
  time-to-resolution, outcome), options (greeks, expiry, strike, IV).

**Where the pure model genuinely bends (be honest):**
- **Equities** — not 24/7: session calendar (overnight gaps, after-hours),
  corporate-action adjustment (splits/dividends), finite/short-borrow. All
  carried by the Market; the strategy stays unaware.
- **Prediction markets** — price is an implied probability in [0,1] with a
  discrete resolution event and binary payoff. Instrument gains
  `resolution: {date, outcome}` and payoff semantics; ExitRule gains
  `hold_to_resolution`; native indicators (implied prob, time-to-resolution,
  prob momentum). The Strategy concept still holds — only the exit/payoff
  model extends.
- **Options (later)** — expiry + strike + greeks + multi-leg. Carry arbitrary
  Instrument metadata now so it's not a wall later; don't build until real.

**Honesty, per market:** a crypto fee/slip model on a stock backtest is a
lie; ignoring session gaps or borrow cost is a lie; treating a prediction
contract as a continuous series is a lie. Each Market carries its own
truthful mechanics; backtest=live holds within each market.

---

## What dies from the current system

- **"Engine"** as a concept — it was a hand-coded bundle of conditions with a
  couple of exposed knobs. Replaced by `Strategy = composition of standard
  indicators`. Old engines become presets.
- **`fleet_config.json`** — strategies become per-user DB rows.
- **Hardcoded constants** (`RISK`, `MAX_CONC`, fees, kill-switch in
  `paper_trader.py`) — become editable `Fleet.account` fields.
- **Single-tenant assumptions** — one config, one box, one account set.

## Connection plan — how the pieces wire together

The catalog (Supabase `pf_*`) and the live runtime (`/api`) are two planes
joined by bot `name`/`id`. The missing organ between them is a **write/compute
backend**. Build order, each slice lighting up dormant schema:

0. **The weld** — canonical strategy = the `core/` spec, stored as
   `pf_bots.spec` (jsonb). `core/mapping.py` converts legacy
   `family_slug` + `params` → spec, so the 29 existing bots backfill. One
   source of truth: build in Studio = backtest = run live = copy.
1. **Engine service** (`core/service.py`) — **API-first**. Endpoints
   (`/v1/validate`, `/v1/backtest`, `/v1/checks`, `/v1/catalog`,
   `/v1/healthz`) are thin HTTP over plain functions in `ENDPOINTS`; an MCP
   server or a direct API caller is the SAME thin layer over those functions.
   Writing full `pf_backtests`/`pf_checks` from here turns the Research
   pipeline + Studio real. (Checks battery = `core/checks.py`: cost-stress,
   entry-delay, placebo — the honesty tests, as instruments not gates.)
2. **DB-driven fleet** — `paper_fleet` loads live bots from `pf_bots`
   (stage=live) instead of only `fleet_config.json`; per-bot paper account.
   Multi-tenant: scan once, evaluate every user's spec.
3. **Events + Feed** — a `pf_events` stream (entries, exits, new-highs,
   graduations, copies, follows) → Feed (home, chronological) + Leaderboard
   (ranked). Same spine, two lenses. A copy is the upvote; the market is the
   judge.
4. **Studio → full loop + NL onboarding** — Studio writes bots; "describe
   your strategy" → LLM → core spec (validated by `core.parse`).
5. **Social + billing** — copy (clone spec → new bot + fresh account),
   follows, plans.

## Information architecture — two worlds

- **BUILD = Studio.** One home to make AND test a bot. Backtesting lives
  here (compose → backtest → validate → launch). The indicator palette and
  market picker are *tools inside Studio*, not top-level destinations.
  "Research" is not a separate place — it is Studio's test/validate stage.
- **COMPETE = Fleet · Feed · Leaderboard.** Run, watch, rank. Bot/Builder
  profiles for inspect/copy/follow.

One verb per surface; no overlap. Nav: BUILD (Studio) / COMPETE (Fleet,
Feed, Leaderboard) + Settings.

## Church & state — what ships vs what stays private

Three layers, regardless of open-source vs closed:
- **Product** (ships): `core/` engine, `web/`, the dashboard + engine
  service. The machine.
- **Alpha** (never ships): tuned strategies (`fleet_config.json` params),
  the 60-ticker Invo universe, the regime dials. The edge — *not* "config".
- **Lab** (doesn't ship): `Invo/`, `research/`, `master/`, `reports/`,
  `backtest/` caches, `hl_bot` live path. The proof + notebook.

Business model is open — the product is **free to use** (sign up, paper
everything); the only thing worth gating is **going live with real money**
(a future `live-fleet.presencenet.io` tier). Open-core (free engine, hosted
product) stays on the table; the Lab split buys that option without deciding
now. Physical repo split is deliberately deferred (destructive) — the Alpha +
Lab layers simply never enter any public repo.

## Open build questions (not yet decided)

- Backtest job runner: queue + worker tech, and how far back / what
  resolution per market.
- Indicator source: TA-Lib (C dep) vs a pure-Python equivalent for the
  custom indicators and the live path.
- Live execution safety per venue (order types, partial fills, the untested
  live order path flagged in `README.md`).
- Billing surface (`SettingsPlan`) and sharing (`SettingsSharing`).
