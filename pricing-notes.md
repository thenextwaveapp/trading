# Paper Fleet — pricing notes

Working notes. Numbers are indicative, not final.

## Model in one line

Free to build and prove; paid to execute (fee on live volume) plus a subscription
for power builders (heavy compute, multi-asset, API).

## Tiers

### Free — paper trading + sandbox ($0/mo)

- Full Build: Compose, Train, Trials, Weather (historical data)
- Multi-bot Roster
- Paper Fleet deploy — standard virtual budget ($10k paper per bot)
- Leaderboard, Feed, basic AI Assistant runs

### Live Fleet — capital & execution

- Per-trade fee on executed **live** orders: ~0.05–0.1% (or a markup on exchange
  execution fees)
- Applies only when a Builder switches a Fleet to live money; fee shown alongside
  P&L
- Same engine runs paper and live, so this is the only thing that gates on real
  capital

### Pro / Builder — subscription (~$49/mo)

| Feature / limit | Free | Pro |
|---|---|---|
| Active deployed bots | 3–5 | 20+ / unlimited fleets |
| Grid sweeps | standard (small grids) | high-concurrency parameter search |
| Engine worker priority | standard 10s poll | high-priority dispatch |
| Backtest history | 2 years | full multi-year, 1m/tick resolution |
| Asset classes | crypto spot/perp | + equities, futures, FX |
| Challenges | enter community challenges | host & publish custom locked-rule challenges |
| Alerts | web notifications | ntfy, webhooks, Telegram/Discord |

## API

### What it enables

- Programmatic strategy generation + backtest/sweep job enqueue (headless)
- Pull structured performance results back (JSON/CSV)
- Stream bot events (`pf_events`: entries, exits, Weather triggers, kill-switch)
  to webhooks / Discord / Telegram
- Route evaluation signals to custom execution bridges beyond Hyperliquid/Binance
- Optional: Python SDK (`pip install paperfleet`) over the same endpoints

### API tiers

| Tier | Access | Includes |
|---|---|---|
| Free | read-only | public endpoints (leaderboard stats, public bot profiles) |
| Pro (~$49/mo) | standard developer API | API keys, ~60 req/min, submit bots + enqueue backtests, event webhooks |
| Quant / Enterprise (~$149–299+/mo) | high-throughput API + WebSockets | high-concurrency sweeps, priority worker queue, real-time streaming (marks/executions), extended tick/1m history |

## Flywheel

1. Free to express — build, train, test against placebo controls, climb the
   Leaderboard.
2. Paid to execute — live-volume micro-fee when proven strategies go to real
   money; subscription for power builders needing heavy compute, multi-asset, and
   API.

## Paywalls

Every point where Free converts, ordered by how central it is.

**Core revenue**

1. **Live capital** — paper is free; flipping a Fleet to real money takes a
   per-trade fee (~0.05–0.1%). The main gate, and the cleanest: you only pay when
   real money is in play, so the platform wins when the builder does.

**Subscription gates (Pro / Builder)**

2. **Fleet size** — 3–5 deployed bots free → 20+/unlimited. Captures fleet
   managers, who need scale by definition.
3. **Compute / grid sweeps** — small grids free → high-concurrency parameter
   search. Captures quant craftspeople; compute is a real cost, so it meters.
4. **Worker priority** — 10s poll free → high-priority dispatch. Captures
   impatience; serious iterators pay for latency.
5. **Backtest depth** — 2 years free → full multi-year, 1m/tick. Captures
   rigorous backtesters; deeper data = more infra.
6. **Asset classes** — crypto free → equities / futures / FX / predictions.
   Captures multi-market operators; each is real engine capability.
7. **Alerts & integrations** — web notif free → ntfy / webhooks / Telegram /
   Discord. Captures operators who can't babysit a fleet, and doubles as
   distribution.
8. **Challenge hosting** — enter free → host & publish custom locked-rule
   challenges. Captures tournament hosts / DAOs / brands.

**Developer layer (API)**

9. **API access** — read-only public data free → developer API (~$49, ~60
   req/min, submit bots + enqueue backtests + event webhooks) → Quant/Enterprise
   (~$149–299+, high-concurrency sweeps, priority queue, WebSocket streaming,
   extended tick history). Scales with compute.
10. **AI Assistant** — basic prompt runs free → heavier/priority builder runs.
    LLM calls are a cost, so it meters naturally.

**Demand-side / later (not built)**

11. **Copy / allocation take** — a performance or allocation fee when capital
    allocators copy-trade proven bots.
12. **Staking split** — a take-rate when stakers back top bots for a fee share
    (token-adjacent; parked).

Spine: #1 is the revenue, #2–#8 the subscription, #9–#10 the developer upsell,
#11–#12 demand-side money once the leaderboard is trusted.
