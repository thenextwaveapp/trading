# Paper Fleet

Paper Fleet is a league for trading strategies.

**Build a fleet of bots that make you money in your sleep — and prove every one
of them works before a dollar's at risk.**

Updated: 2026-11-01.

---

## What it is

Four verbs, one game:

- **Build** — compose a bot: name it, give it a face and a color, pick a family,
  tune its Setup.
- **Train** — a bot earns its place through Training → Trials → Weather before
  it can battle. Nothing is faked into the Roster.
- **Command** — your Fleet is your army; the control center is where you run it.
- **Battle** — real P&L, not simulated flavor.

Three references fused:

- **SuitU** — Libii's fashion dress-up game
- a **military command center** — command a force
- **Hyperliquid** — real perps, real P&L, don't lie

Every stat is a verified track record. One engine tests a strategy and trades
it — no bot grades its own homework.

Make it fun to raise Bots, keep the scoreboard honest, and let the market write
the story.

## The bigger idea

Paper Fleet turns trading strategies into persistent, public characters in a
market that keeps changing. Each Bot has an identity and a history: how it was
built, how it was tested, who adapted it, and what happened when it met the
market. The result is more than a collection of trade logs; it is a growing
record of trading ideas taking shape and spreading in public.

The flywheel is simple: people build Bots because creation is expressive; the
market gives each one a continuing story; results invite comparison and
discussion; and those stories bring in more Builders and experiments. The
Pokémon metaphor captures the roster, identity, progression, and competition.
Here, the Bots are strategies, and the arena is the market.

The ambition is for people to arrive curious about trading and stay invested in
the Bots: their own, their friends', and the unexpected ones they want to keep
watching. Their experiments deepen the shared world and the data it produces.

### The data

Every Bot can generate a longitudinal record that connects its strategy and
versions to its backtests, stress tests, market conditions, deployments, and
paper-trading outcomes. Across Bots, this makes it possible to study not only
which strategies performed, but how they changed, where they worked, how they
were discovered or copied, and how their results evolved as markets changed.

Over time, that record could become a map of strategy culture forming in
public: which ideas emerge, how they spread, what Builders learn from one
another, and how the market responds. The value is in connecting the full
journey—not treating every backtest, trade, or leaderboard rank as an isolated
data point.

### Product guardrails

- **Make the capital mode unmistakable.** Paper and live trading have different
  stakes. Paper trading is free. When a Builder deliberately switches to live
  capital, real money is on the table and the platform takes a small fee per
  trade, shown clearly alongside P&L. The change must be explicit, clearly
  signaled throughout the experience, and protected from accidental activation.
- **Treat copying as a starting point, not a promise of scalable returns.**
  If many accounts follow the same Bot, crowded entries can change the fills
  and outcomes that made its record attractive. Make a Bot's setup and
  constraints visible where appropriate, and give Builders room to adapt and
  test their own versions rather than treating a leaderboard rank as an
  instruction to follow blindly.
- **Make market context legible.** Strategies behave differently as conditions
  change. When Weather keeps a Bot out of the market, show the conditions and
  evidence behind that decision so Builders can understand why it is waiting.

## How it started

This began as a single-owner system. We mined **15,713 trades from 52 top Invo
traders** (Feb 2024 → Oct 2026), reverse-engineered the market conditions behind
their entries, and traded the *setup* on Hyperliquid — not copy-trading. The
finding that held up: their big wins are shorts into parabolic small-cap pumps,
and the entry timing is a real, measurable edge (see [The Lab](#the-lab-the-proof)).

That became a live paper fleet of strategy variants, each earning its own verdict
from its own account. The product is the generalization: the tooling that let one
owner do it, opened up so anyone can — without touching code.

## Direction

A **multi-tenant SaaS** where any Builder runs the whole pipeline through the UI.
The product is the **machine, not the signals** — ship the tooling, not the edge.

- **Market-agnostic core.** crypto → stocks → predictions is adapters, not
  rewrites. The engine already scans a market once and evaluates many bots
  against the same candles; multi-tenant is just "those bots belong to different
  Builders" (one scanner → N evaluators).
- **Editable vs locked** is the product spine. A bot = `{family (fixed menu) +
  Setup (editable) + universe (selectable)}`. Editable: entry/exit params,
  sizing, concurrency, account, alerts. Locked: family logic, universe
  construction, fee/fill model, paper accounting.
- **Three buckets.** **System** = the running machine (`core/` + `runtime/` +
  the Fleet). **Process** = the pipeline, shipped inside the product as Build.
  **Lab** = `lab/`, the owner's proof-of-concept; it does not ship.

## Lexicon

Canonical vocabulary — **one concept, one word, from the DB field to the button
label.** Where they drift, the product lies to itself.

| Word | Meaning | Backing |
|---|---|---|
| **Bot** | a strategy | `pf_bots` |
| **Builder** | the human | `pf_profiles` |
| **Roster** | home screen — all your bots, every stage | — |
| **Fleet** | your *deployed* (trading) bots | runtime |
| **Setup** | a bot's editable params (runup/vol/hold/stop/sizing…) | `pf_bots.params` |
| **Family** | archetype (pump_short, momo, capit, loser, churn, books) | `pf_strategy_families` |
| **Universe** | the tradeable coin set | `pf_universes` |
| **Battle** | what a Deployed bot does | real P&L |
| **Leaderboard / Follow / Copy / Feed** | the social layer | `pf_follows`, `pf_events` |

**Two axes, never crossed.** A bot is **Deployed** (answers *is it working?*).
The capital is **Live** (answers *is the money real?*). The product flips **Paper
Fleet → Live Fleet** when you fund it with real money — logo and banner change;
"Live" is reserved for that switch alone. "Paper Fleet" is a pun: paper
(paper-trading, honesty in the name) + paper (money) + Fleet (the army),
paper-airplane logo.

## Screens & flows

The target experience, described as it should be — not the stubbed state the code
is in today.

**Roster** (`/`) — home, and the heart of the game. Your bots laid out with their
face, level (stage), and record. At a glance: who's training, who's Ready, who's
Deployed and battling, who's winning. A living roster you command.

**Build** (`/build`) — the flow that takes a bot from idea to Deployed:

- *Compose* — name the bot, give it a face, pick a Family, tune the Setup; a live
  preview shows exactly what it will trade.
- *Training* — it runs over years of history: equity curve, trade count, win
  rate, drawdown, all after fees.
- *Trials* — the honesty gauntlet; each trial passes or fails in the open.
- *Weather* — the regime gate: when the bot is allowed to fight.
- *Ready → Deploy* — it graduates, and you deploy it to the Fleet.
- *Report* — its record, shareable.

**Bot profile** (`/bot/:name`) — a bot's full, honest stat sheet: its Setup,
verified track record, equity curve, every battle, which Trials it passed. The
page that proves the bot is real.

**Leaderboard** (`/leaderboard`) — every public bot ranked by real P&L. **Follow**
a Builder, **Copy** a bot into your Roster as a Draft to train yourself. The
social arena where a verified record is the currency.

**Builder profile** (`/builder/:handle`) — a Builder's bots, reputation, and
followers. Your identity and collection, public.

**Command center** — the war room for your Deployed Fleet: live positions marked
to market, P&L, the Feed of entries/exits/kills, fleet health, alerts. (Today in
`runtime/fleet_dashboard`; it folds into the app.)

**Settings** (`/settings`) — account, alerts, and the control that flips the
product **Paper Fleet → Live Fleet** when you fund it with real capital.

Key flows:

- **First run** — a Builder signs up, a starter fleet is seeded automatically
  (the signup trigger), and a guided first Build gets their first bot moving.
- **Build → Deploy** — compose → Training → Trials → Weather → Ready → Deploy,
  each step showing real results as the bot earns them.
- **Discover → Copy** — find a bot on the Leaderboard → Copy it → it lands in
  your Roster as a Draft to retune and train as your own.
- **Paper → Live** — fund with real capital → the product flips to Live Fleet →
  Deployed bots battle real money, same engine, same bots.

## Build (the pipeline)

Every bot climbs the same ladder; `pf_bots.stage` is the rung it's on.

| Stage | What happens | Engine |
|---|---|---|
| **Draft** | composed, never fought | — |
| **Training** | run over years of history | `core.backtest` → `pf_backtests` |
| **Trials** | advisory stress tests (below) | `core.checks` → `pf_checks` |
| **Weather** | regime breakdown → rules of engagement | `core.conditions` → `pf_conditions` |
| **Ready** | weather gate closed, awaiting orders | — |
| **Deployed** | battling in the Fleet | `runtime/` |

**Trials — the stress tests.** Trials rerun the strategy under less favorable
assumptions and compare it with random-entry placebos. They help show how
sensitive the result is, but are advisory: every completed run lands on Trials,
and Weather is where the gate is set.

**How to read the evidence.** Training is the baseline backtest: how the
strategy performed on historical data under the configured assumptions. Trials
stress that same strategy against less favorable assumptions and random-entry
placebos, to show how sensitive the result is. Weather breaks historical
performance down by Bitcoin trend and market volatility, helping Builders see
where the strategy tended to work or struggle and optionally set conditions for
deployment.

These steps do not prove that a strategy will keep working. They organize
historical evidence and make its assumptions, sensitivities, and context easier
to inspect; future market behavior remains unknown. Skill matters, but luck
does too—that uncertainty is part of the market, not a flaw in the scoreboard.

## Codebase map

The app is three real layers around one idea — bots earn a verified record, then
trade. Roughly 145 Python files, 68 TS/TSX, 16 SQL.

**The engine (Python) — `core/` + `runtime/`.** The brain.

- `core/` is the library: `strategy.py`, `evaluator.py`, `backtest.py`,
  `indicators.py`/`talib_wrap.py`, `conditions.py`/`expr.py` (the editable rule
  DSL), `regime.py` (Weather), `challenges.py`/`checks.py` (the Trials
  gauntlet), `equity.py`, `marketdata.py`/`markets.py` (market adapters),
  `sweep.py` (parameter search). The "one engine tests a strategy and trades it."
- `runtime/` is the running machine: `engine_worker.py` (the Build worker),
  `market_scan.py`, `paper_fleet.py`/`paper_trader.py` (the live paper fleet),
  `challenge_runner.py`, `news_scan.py`, `backfill_curves.py`,
  `fleet_dashboard.py`, `pf_db.py`, `spec_runtime.py`. Runs 24/7 on Hetzner.

**The data spine — `db/` + `supabase/`.** Postgres on Supabase: `schema.sql`,
`functions.sql`, `policies.sql` (RLS), `migrations/` — the
`pf_bots`/`pf_profiles`/`pf_universes`/`pf_follows` world. Edge functions in
`supabase/functions/`: `parse-strategy` (natural language → Setup) and `assistant`.

**The web app — `web/` (React + TypeScript + Vite).** `src/routes` (Roster,
Build, Bot profile, Leaderboard, Challenges, Feed, Market, Settings),
`src/components` (charts, tables, drawers, ⌘K search palette), `src/assistant`
(the AI builder), `src/api`/`src/db` (Supabase client), `auth.tsx`. Render-only;
the engine owns the data.

**The Lab — `lab/`.** The owner's proof-of-concept that does not ship: `Invo/`
(the 15,713-trade mining), `bn/` (Binance data), `master/`, `backtest/`,
`research/`, `reports/`.

**Live & ops.** `live/` — the real-money bridge (`bot.py`, `check_parity.py` for
paper-vs-live parity, keys). `deploy/` — `systemd/` (Hetzner prod) + `launchd/`
(local dev). `paper/fleet/` + `fleet_config.json` + `universe60.json` — the fleet
roster config. `archive/` — retired code (`legacy-engine`, `hl_bot`, `dashboards`).

In one line: a Python engine scans a market once and evaluates many bots against
the same candles → writes verified records to Postgres → a React app renders the
roster/leaderboard, with a no-code AI builder on top, a research Lab to the side,
and a real-money bridge for graduation.

## Architecture

```
web  ──insert pf_backtests / pf_sweeps (pending)──▶  DB  ◀──drain & write back──  runtime/engine_worker
 ▲                                      │                                    │
 └──────────────── reads ───────────────┘                            core/ (the one engine)
```

The web **never calls the engine**. It enqueues work by inserting a row; the
worker is the only thing that runs a bot, through the same `core/` engine the
Lab and live Fleet use (the test and the live trade run the same code path); it
writes results back to the DB, the single source of truth the web reads.

| Dir | What |
|---|---|
| `core/` | the engine library — indicators (211, full TA-Lib + ROC/VOL_RATIO/WICK_FRAC), `expr`/`strategy`/`evaluator`, `backtest`, `checks`, `conditions`, `regime`, `markets` (capability model, `inputs ⊆ provides`), `universe`, `service` (endpoints), `db` |
| `runtime/` | the services — `paper_fleet`, `fleet_dashboard`, `engine_worker` (the Build worker), `fleet_source`, `pf_db` (service-key DB helper), `spec_runtime` |
| `db/` | version-controlled Supabase schema: `schema.sql` + `policies.sql` (RLS, owner-scoped) + `functions.sql` (signup trigger, event emitters). Apply order in `db/README.md` |
| `web/` | the React SPA (Vite, HashRouter) — live at fleet.presencenet.io |
| `lab/` | the proof-of-concept research (does not ship) |
| `tests/` | engine self-tests — `python3 -m tests` reproduces legacy signal/exit bar-for-bar |
| `deploy/` | deploy units — `systemd/` (Hetzner box) + `launchd/` (Mac) |
| `live/` | the Hyperliquid go-live package (dry until armed) |

Root keeps the live-side config: `fleet_config.json`. (The older `hl_bot.py`
execution bot + its `bot/` state are archived under `archive/hl_bot/`; the
`live/` package supersedes it.)

## Current state

- **Engine** (`core/`) built + tested; selftests green (`python3 -m tests`).
- **DB** multi-tenant: RLS on all `pf_*` tables, signup trigger seeds a starter
  fleet, `pf_events` emits trade/copy/follow events. See `db/README.md`.
- **Web** reads the catalog, Markets model, and live Leaderboard; the first real
  write landed — Build saves a Draft bot the signed-in Builder owns.
- **Build worker** (`runtime/engine_worker.py`) drains pending backtests →
  runs `ep_evaluate` once → writes results, Trials and Weather, persists the
  deployable `spec`, flips stage to `trials` (or `draft` on error). It also
  drains `pf_sweeps` → `ep_sweep` → `pf_sweep_runs` for the parameter grid in
  Build. Has a `--once` drain mode.

- **Lexicon reconciled** — schema obeys the words: `pf_bots` dropped `status`
  and `engine`, folded the sizing knobs into `params`; `stage` values are
  `draft/training/trials/weather/ready/deployed`; the web `Research` flow is now
  `Build` (`routes/build/`, `/build`). tsc + vite green. Not yet applied to the
  live Supabase DB.

**Next:**

1. Apply `db/migrations/20261024_build_flow.sql`,
   `db/migrations/20261024_weather_thresholds.sql` and
   `db/migrations/20261025_checks_lexicon.sql` to the live Supabase DB.
2. Run `runtime.engine_worker` as a service (units live in `deploy/`).

## Feature surface

What a Builder can do and set, and what runs underneath each. The `core/` engine
used to backtest a bot is the same code the runtime uses to trade it: entry/exit
logic, fee/fill model, and sizing are shared; the differences are the data source
(historical candles vs. live API) and the accounting (pooled trades in backtest
vs. per-position state live). The web does not call the engine — it inserts a row
in Postgres, `runtime/engine_worker.py` drains it, and results are written back.

**Roster / Fleet (home).** Bots by stage with face, color, record, and live
return; aggregate fleet equity (`FleetView`/`FleetChart`); fleet state
(Running / Paused / Stale / Errors) and position management (`ManagePosition`).
→ `runtime/paper_fleet.py` + `paper_trader.py` run the paper-trading loop and write
live state via `runtime/pf_db.py` (service key) to `pf_bot_marks` /
`pf_bot_trades` / `pf_fleet_log`; the web reads those tables.

**Build flow (`/build`).** Each step calls a `core.service` endpoint;
`runtime/engine_worker.py` is what invokes them after draining a pending row.

- *Compose* — name, face, color, a **Family** (pump_short, momo, capit, loser,
  churn, books), a **Setup**, a **Universe**, and a preview.
  → `core/strategy.py` parses the spec into `_books` (`side:"both"` becomes a long
  book and a short book); `core/params.py` defines each editable field (kind,
  min/max, `visible_if`, backtest/live/sweep flags); `core/export_catalog.py`
  serves the palette (`ep_catalog`).
- *Setup params (the rule DSL)* — entry/exit as a condition tree: AND/OR/NOT groups
  over comparisons (`lt`/`le`/`gt`/`ge`/`eq`/`crosses_above`/`crosses_below`) of
  operands that are numbers, indicator references (with `offset` for prior bars,
  optional `symbol`/`tf` for cross-asset / multi-timeframe), or arithmetic — plus
  direction, stop (`hh`/`dstop`/`sig`/`trail`/`none`), take-profit, NATR trailing,
  hold bars (`time_bars`), timing (UTC hours/days/date ranges), `fresh`, and
  concurrency.
  → `core/expr.py` (`eval_node`) with guards in `core/evaluator.py`: index/lookback,
  gapless tape, alive-bar (not a doji, last 9 bars volume > 0), timing, and
  cross-series alignment to the most recently closed aux bar (causal).
- *Indicators* — 211 registered: pure-Python `core/indicators_std.py`
  (SMA/EMA/WMA/DEMA/TEMA, RSI/CMO/MOM/CCI/MACD, ATR/NATR/Bollinger/ADX, MFI/OBV)
  plus ROC / VOL_RATIO / WICK_FRAC / CLOSE_POS in `core/indicators.py`; TA-Lib
  indicators register behind the standard ones when the C library is present, so
  ids stay stable across hosts. A market exposes an indicator only when its
  `inputs ⊆ provides` (`core/markets.py`) — e.g. volume indicators are unavailable
  on FX (OHLC, no volume).
- *Sweep* — parameter grid search over spec paths (e.g. a period over
  {14, 20, 28}). → `ep_sweep` / `core/sweep.py`; the candle tape loads once per
  universe and is reused across grid points → `pf_sweep_runs`.
- *Training* — backtest over the training window (default 730 days,
  `BUILD_TRAIN_DAYS`): equity curve, trade count, win rate, drawdown, after fees.
  → `ep_evaluate` → `core/backtest.py:backtest_universe` (per-ticker replay, pooled
  trades, `summarize` compounds the equity curve) → `pf_backtests`.
- *Trials* — cost stress (3× fees), 1-bar entry delay, and a placebo test (the
  strategy's mean net must exceed the 95th percentile of 100 random-entry rounds).
  Advisory, not a gate. → `core/checks.py` → `pf_checks`.
- *Weather* — a 3×3 grid of BTC trend × volatility terciles with the mean return
  of trades in each cell; `condition_filter` lists which cells may trade. Computed
  for reporting in backtest; applied to entries when deployed.
  → `core/conditions.py:conditions_breakdown` → `pf_conditions` →
  `pf_bots.condition_filter` (live gate via `runtime/spec_runtime.py`).
- *Deploy* — a Ready bot with a complete spec joins a Fleet on a $10k paper budget
  (stage → `deployed`). → `runtime/spec_runtime.py:covered()` first checks the spec
  is one the live path supports (rejects partial specs, unsupported stop modes,
  limit orders).
- *Report* (`/build/report/:name`) — backtest vs. live, equity curve, every trade,
  Trials passed — read from the result tables.

**AI Assistant builder.** A natural-language description is turned into a Setup by
`web/src/assistant` + the `parse-strategy` Supabase edge function, which emits the
spec shape `core/strategy.py` consumes.

**Bot profile** (`/bot/:name`). Setup, track record, equity curve, trades, and the
Trials passed — rendered from the result tables; the web does not recompute them.

**Leaderboard + Challenges.** Bots ranked by live P&L, filterable by Market and
Challenge. A Challenge is a Copy with a locked template — some Setup fields fixed,
others open. → `ep_enter_challenge` validates an entry against the lock-set;
`ep_score_challenge` ranks it.

**Feed + social.** Event feed, Follow, Copy, and lineage via `copied_from`.
→ `pf_follows` / `pf_events`.

**Market.** Market and detail pages, candle charts, news, ⌘K search palette.
→ `runtime/market_scan.py` upserts `pf_market_snapshot` every 60s (Binance 24h
ticker + CoinGecko metadata); `runtime/news_scan.py` provides news.

**Settings.**

- *Profile* — photo, timezone, sharing. *Plan* — Free / Live.
- *Bots / Fleets* — defaults, starting capital, max concurrent, drawdown threshold
  (feeds the kill-switch in `runtime/paper_fleet.py`: drawdown past −5% over 7 days
  pauses new entries for 3 days).
- *Market data* — source (local `lab/bn` gzip cache vs. live Binance/Yahoo),
  freshness/stale detection, last-mark.
- *Trading engine* — state (Running / Paused), health.
- *Alerts* — ntfy pushes on entry/exit/kill. *Coins* — universe defaults.

**Account.** Auth (`SignIn`, `AuthModal`, `RequireAuth`), Privacy, Landing.

**Paper → Live.** Funding a Fleet with real capital flips Paper Fleet → Live Fleet:
the same bots run the same `core/` path (`runtime/spec_runtime.py`); logo and
banner change, the per-trade fee is shown with P&L, and the switch is guarded
against accidental activation.

**Build execution path.** The web inserts a pending `pf_backtests` / `pf_sweeps`
row; `runtime/engine_worker.py` drains it (10s poll, or `--once`), runs the `core/`
endpoint, writes `pf_backtests` / `pf_checks` / `pf_conditions`, and sets
`pf_bots.stage`; the web reads the result. The engine is not called from the
browser.

## Feature map

Every line resolves to a page, a field, or the editable-vs-locked line. Tagged
**[have] / [partial] / [new]**.

**Make & train**

- **Build a Bot** *[have]* — `/build/compose`. Compose from a **Family** (archetype,
  `pf_strategy_families`), a **Universe** (coin set, `pf_universes`), a **Setup**
  (editable params, `pf_bots.params`), and a direction. Saves as a Draft in `pf_bots`.
- **Train → Trials → Weather** *[have]* — the Build ladder. **Training**
  `/build/training` runs the backtest over years of history (`pf_backtests`).
  **Trials** `/build/trials` runs the advisory stress tests (`pf_checks`).
  **Weather**
  `/build/weather` maps performance across BTC trend × volatility and saves the
  gate (`pf_conditions` → `pf_bots.condition_filter`), which
  `runtime/spec_runtime.py` enforces on live entries.
- **Deploy** *[have]* — `/build/deploy`. A Ready Bot with a complete spec
  graduates: pick Fleet + visibility, it joins on a $10k paper budget and starts
  battling (stage `deployed`, real P&L). Partial specs are blocked.
- **Report** *[have]* — `/build/report/:name`. A Bot's full record: backtest vs
  live, equity curve, every trade, the Trials it passed.
- **Versions** *[have]* — every save snapshots the Setup to `pf_bot_versions`,
  deduped by a strategy fingerprint so only real changes add a row, with
  `pf_bots.version` kept in step. Editing a Bot (the **Edit** button on its
  profile, which reopens it in Build) preserves the prior Setup as its own
  version *before* the change lands — so a strategy's history is append-only and
  the old version keeps its row even as the Bot moves on. Lineage across Bots is
  in `copied_from`. *Still to come: the side-by-side backtest compare across
  versions, and attributing a Bot's live trades to the version that produced
  them (today the ledger hangs off the Bot, not the version).*

**Collect & command**

- **Roster** *[have]* — `/` home. Every Bot you own, laid out by stage, with its
  face, record, and live return.
- **Fleet / command center** *[have]* — `/fleet`. Deployed Bots marked to market:
  positions, P&L, the Feed of entries/exits/kills, fleet health, with pause and stop.
- **Fleets as squads** *[partial]* — group Bots into named Fleets (`pf_fleets`),
  each with its own budget and check interval; the sidebar lists them.
- **Alerts** *[partial]* — `/settings`. ntfy pushes entries, exits, and kill-switch
  trips to your phone (runtime emits these today).
- **Retire** *[new]* — freeze a Bot: it stops trading and keeps its verified record
  on your Roster as a finished run.

**Compete**

- **Leaderboard** *[have]* — `/leaderboard`. Every public Bot ranked by live P&L,
  with a podium and a full table (win rate, streak, sparkline). Filter by **Market**
  (Crypto, Stocks·soon, Predictions·soon) and by **Challenge**.
- **Challenge** *[new]* — a Copy with a locked template: some Setup fields stay
  fixed, others stay open, so everyone tunes the same thing (Universe-only, one-knob,
  timeframe-only — the lock-set defines it). Carries an optional expiry date and a
  sealed-until-close option. You **enter** one from the Leaderboard and **publish**
  one from a Bot; its board is the Leaderboard filtered to that Challenge.

**Social**

- **Copy** *[partial]* — from the Leaderboard or a Bot profile, clone a public Bot
  into your Roster as a Draft to retune (`copied_from` records the source).
- **Follow** *[partial]* — from a Builder profile `/builder/:handle`, track a
  Builder and get their new Bots (`pf_follows`).
- **Lineage** *[new]* — a Bot shows "descended from X" and its pedigree, read from
  `copied_from`.
- **Builder profile** *[have]* — `/builder/:handle`. A Builder's Bots, reputation,
  and followers — their public identity and collection.

**Capital**

- **Paper → Live** *[new]* — `/settings`. Flip a Fleet to real capital: the same
  Bots on the same engine trade real money; the logo and banner switch to Live.

## Challenges (the SuitU loop)

The social hook: a constrained competition cycle that turns building into a game.
Every Challenge is a theme prompt with locked rules, so everyone competes on the
same footing and the market does the voting.

1. **The "Theme Prompt" = the Challenge Spec.** A new prompt drops on a cadence
   (e.g. "The Volatility Storm": fixed universe SOL/NEAR/DOGE, fixed 5m
   timeframe, sizing and exits open; "The Clean Slate": fixed family
   `pump_short`, universe open, max hold locked to 1h; "No Weather Allowed":
   regime filters disabled, raw strategy vs pure market chaos).
2. **The "Submission & Lock" phase.** A 24–48h Build Window to compose, tune,
   Train → Trial, and submit. Entries can be **sealed** — Setups stay hidden
   until the market window closes, so no last-minute copycatting.
3. **The "Market Event" = the voting phase.** Submitted bots deploy into the
   same live paper arena for a 72h market window; the market itself votes.
   Everyone watches the Challenge Leaderboard move as candles print, with the
   Live Feed showing your bot fighting alongside hundreds given the same
   prompt/constraints.
4. **The Post-Match breakdown & copy meta.** When the timer hits zero: Setups
   unseal; the winner's profile shows Win Rate, Max Drawdown, Equity Curve, and
   a "Fork This Setup" button; top placements earn verified badges (e.g.
   "Vol Storm #1 Champion").

Why it's a growth engine: it destroys option paralysis (a focused prompt tells
you exactly what to build today), creates an infinite content cycle (a new
prompt every week), and fuels pure bragging rights and a strategy "Meta" debated
on Discord/X. It runs SuitU's core loop — Prompt → Expressive Build → Public
Arena → Comparison & Meta — on top of real market P&L.

## The Lab (the proof)

The research behind the origin, in full in `lab/reports`. These findings come
from historical tests of strategies derived from the Invo trade data. They
document that research, not product-wide promises or expected results:

- Trader entry timing beat random by +0.55%/4h, ~13σ,
  robust across quarters/regimes/traders. The phenomenon: shorting parabolic
  small-cap pumps.
- ML extraction failed out-of-sample twice — the edge is in trade
  *selection*, not averaged features.
- **Rule P**, the pump-short strategy derived from the Invo data, passed its
  pre-registered historical test. Its results belong to that research case
  study, not a general forecast.
- The signal was regime-dependent: it lost in 2023–24; regime flipped ~early
  2025. The Weather dial exists because of this.
- Point-in-time universe testing showed how strongly results can depend on
  universe construction and lookahead. The lesson: evaluate strategies with
  realistic universes and costs, and compare research results with subsequent
  Fleet performance.

### Rule P — historical Invo-data research example

Rule P was a pump-short strategy developed from the mined Invo trader data and
tested against historical market data. Its rule definition and research results
are preserved in the linked reports as a case study in the project's origins;
they are not defaults or performance claims for Bots built in Paper Fleet.

`lab/` map: `Invo/` raw scrapes · `bn/` Binance data · `master/` consolidated
trades + features · `backtest/` candle caches + ledgers · `reports/` timestamped
analysis · `research/` the scripts (`cd lab && python3 research/<script>.py`).

## The research philosophy

The endless combinations of market mechanics, assets, and parameters mean the
universe of viable quantitative strategies is virtually infinite. At its core,
every strategy is built from a simple stack of building blocks: a signal driver
(like price momentum, volatility spikes, or volume imbalance), an entry and exit
trigger, and a risk-sizing rule. By adjusting these variables across different
asset classes, timeframes, and market regimes, you can isolate completely
distinct behavioral edges — from high-frequency arbitrage and trend-following to
mean-reversion crashes.

What makes this pursuit so powerful is that market events are constantly
evolving alongside leverage, liquidity shifts, and trader psychology. Finding an
edge isn't about uncovering a single "holy grail" formula; it's about
systematically testing hypotheses, stripping away noise, and defining precise
rules that turn structural market behavior into repeatable outcomes. The real
opportunity lies in the infinite variations left to explore — there is always
another edge waiting to be translated into a clean, actionable model.
