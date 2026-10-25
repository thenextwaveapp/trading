# Paper Fleet

**Build trading bots, train them until they earn it, and deploy the ones that
pass to battle — on paper money first, real money when you flip the switch.**
The structure is Pokémon; the stakes are a verified track record. Expressive
*and* honest.

Updated: 2026-10-22.

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

**The invariant that makes it not "Pokémon with charts": the bots are real.**
Every stat is a verified track record, never flavor. Backtest == live.

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

**Trials — the honesty gauntlet.** Trials show whether the edge looks real, not
luck. They are advisory: every completed run lands on Trials, and Weather is
where the gate is set.

1. **Survives 3× costs** — edge holds at triple fees + slippage.
2. **Survives a late fill** — edge holds entered one bar late.
3. **Beats random entries** — real net/trade beats the 95th pct of placebo entries.

## Architecture

```
web  ──insert pf_backtests(pending)──▶  DB  ◀──drain & write back──  runtime/engine_worker
 ▲                                      │                                    │
 └──────────────── reads ───────────────┘                            core/ (the one engine)
```

The web **never calls the engine**. It enqueues work by inserting a row; the
worker is the only thing that runs a bot, through the same `core/` engine the
Lab and live Fleet use (so backtest↔live parity holds); it writes results back
to the DB, the single source of truth the web reads.

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
  deployable `spec`, flips stage to `trials` (or `draft` on error). Has a
  `--once` drain mode.

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

## Feature map

Every line resolves to a page, a field, or the editable-vs-locked line. Tagged
**[have] / [partial] / [new]**.

**Make & train**

- **Build a Bot** *[have]* — `/build/compose`. Compose from a **Family** (archetype,
  `pf_strategy_families`), a **Universe** (coin set, `pf_universes`), a **Setup**
  (editable params, `pf_bots.params`), and a direction. Saves as a Draft in `pf_bots`.
- **Train → Trials → Weather** *[have]* — the Build ladder. **Training**
  `/build/training` runs the backtest over years of history (`pf_backtests`).
  **Trials** `/build/trials` runs the advisory gauntlet — beats random entries,
  survives triple costs, survives a late fill (`pf_checks`). **Weather**
  `/build/weather` maps performance across BTC trend × volatility and saves the
  gate (`pf_conditions` → `pf_bots.condition_filter`), which
  `runtime/spec_runtime.py` enforces on live entries.
- **Deploy** *[have]* — `/build/deploy`. A Ready Bot with a complete spec
  graduates: pick Fleet + visibility, it joins on a $10k paper budget and starts
  battling (stage `deployed`, real P&L). Partial specs are blocked.
- **Report** *[have]* — `/build/report/:name`. A Bot's full record: backtest vs
  live, equity curve, every trade, the Trials it passed.
- **Versions** *[partial]* — each Setup change writes a row to `pf_bot_versions`;
  Build shows the new backtest beside the previous one and the Bot it was Copied
  from, so you keep the stronger Setup.

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

## The Lab (the proof)

The research behind the origin, in full in `lab/reports/`. Load-bearing findings:

- **The edge is real.** Trader entry timing beats random by +0.55%/4h, ~13σ,
  robust across quarters/regimes/traders. The phenomenon: shorting parabolic
  small-cap pumps.
- **ML extraction failed** out-of-sample twice — the edge is in trade
  *selection*, not averaged features.
- **Rule P** (the frozen pump-short base) passed a pre-registered gate: 74
  trades, +3.4%/trade, all 7 windows positive, CI [+1.2, +5.9]%.
- **Regime-dependent.** The same signal lost in 2023–24; regime flipped ~early
  2025. The Weather dial exists because of this.
- **Universe-specific and perishable.** Point-in-time universe rebuild (no
  hindsight) cuts tuned-sizing results ~1000×, and a 15-min entry delay halves
  the edge. Lesson baked into the invariant: judge on live Fleet results, PIT
  universe, fees on, taker entry at close.

### Rule P — the short book's base rule

On 15m candles, short at close when ALL hold: (1) `close/close[16] − 1 ≥ 12%`
(4h stretch), (2) `close < prev close` (first red), (3) `volume ≥ 2× mean of
prior 8 bars`, (4) market alive. Stop = max high of the 4h signal window; time
exit 4h; taker fees + slip (0.045%/leg + 0.05%); size =
`min(0.75% equity / stop-dist, 20% equity)`; max 6 concurrent, 1/ticker;
kill-switch −5% equity in 7d → 3d pause. ~+2%/trade, ~2 trades/week, ~53% win.

`lab/` map: `Invo/` raw scrapes · `bn/` Binance data · `master/` consolidated
trades + features · `backtest/` candle caches + ledgers · `reports/` timestamped
analysis · `research/` the scripts (`cd lab && python3 research/<script>.py`).
