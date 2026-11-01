# Paper Fleet — outreach notes

Consolidated from the working sessions: who we target, the approach, and the
lead-gen machine built against the RevenueBase dataset.

---

## 1. Targets — the persona list

Six categories of target personas / stakeholders.

**1. Academic & Educational**
- Student quant / algo-trading clubs (backtesting hackathons, strategy battles)
- Finance / FinTech / CS faculty (live lab for assignments, risk-free learning)
- Campus FinTech & trading labs
- Academic researchers & PhD candidates (agent-based markets, microstructure, RL)

**2. Strategy Creators & Operators (supply side)**
- High-agency quant craftsperson (custom Python/Rust/TS, low-latency, clean backtests)
- "No-code" algo creator (visual logic / templates / AI prompts)
- Strategy modder / forker (clone leaderboard bots, tweak, redeploy)
- High-frequency arbitrageur (cross-venue / cross-chain / spot-vs-perp)
- Fleet manager (20–100 micro-bots for uncorrelated yield)

**3. Capital Allocators & Copy-Traders (demand side)**
- Retail "set-and-forget" investor (follow top verified bots)
- Prop desk / syndicate manager (scout un-credentialed talent, fund winners)
- Strategy staker (stake behind top bots for a fee split)

**4. Exchanges & Infrastructure Partners**
- CEXs / DEXs (Binance, Bybit, Hyperliquid) — API volume / onboarding pipeline
- Market makers & liquidity providers
- Brokerages / Web2 trading platforms (embed the gamified builder)
- RPC / node / MEV infra operators
- Risk engine & liquidation operators

**5. Ecosystem & Social Catalysts**
- Leaderboard streamers / creators (Twitch/YouTube/X bot-vs-bot tournaments)
- Tournament hosts & community organizers (DAOs, protocols, brands)
- Third-party analytics / "leaderboard watchers" (Dune-style trackers)
- Alternative data / oracle providers (news sentiment, macro, on-chain)

**6. High-Level Institutional & Governance**
- VCs & strategic investors (AI agents × quant × gamified UI × liquidity routing)
- Prop desk recruiters (verified logs as a hiring funnel)
- Security & code auditors (vet bot scripts before live funds)
- Regulatory & compliance advisors (sandbox → live, non-custodial / brokerage)
  - NOTE: becomes a founding hire the moment demand-side monetization (copy /
    allocation / staking) goes live. See pricing-notes.md #11–12.

---

## 2. Outreach approach (working thesis — to validate)

- **Seed supply first.** Builders are the cheap cold-start and they create the
  content demand shows up for. Demand (allocators, streamers, prop desks) arrives
  on its own once the leaderboard is live and credible — don't cold-chase them.
- **Sharpest wedge: student quant clubs.** They come in packs (one club = ~30
  builders), are credential-hungry (leaderboard = résumé → prop-desk funnel), and
  a campus / inter-university tournament is a format, not a cold email.
- **The filter for any persona:** does it *create* the scoreboard (outbound now)
  or *consume* it (landing page + patience)?
- The trust substrate for all of it is the un-riggable, same-engine-tests-and-
  trades leaderboard — the thing that makes a verified track record worth
  allocating to.

---

## 3. The lead-gen machine (RevenueBase + Athena)

Repoint the existing cleantech lead-gen apparatus at Paper Fleet's supply side.

### Dataset
- AWS account `817685572899`, region **ca-central-1**.
- `s3://businessoncamera-revenuebase/` — RevenueBase "velocity" export: **~300M
  rows**, 21,763 gzip CSV chunks (~16 MB each, ~365 GB), **173 columns**.
  LinkedIn-enriched person+company records: email + phones, title, headline,
  bio (`about_me`), skills, seniority, firmographics, funding, tech stack, geo.
- Results/work bucket: `s3://boc-athena-results-817685572899/` (Athena output).
- Note: nulls encode as `\N` → render as `"N"` after OpenCSVSerde (cleaned to
  NULL in the Parquet base). Booleans are words (`true`/`false`/`Yes`).

### Philosophy
- **One relevance floor, everything else scores.** The only hard gate is "has ≥1
  clean trading/quant/crypto signal." Geo, email validity, seniority, voice are
  all boosts, never gates — gating cuts good leads.

### Target segments (the WHERE clause → scoring tags)
- **A. Algo/quant builders** — core supply (algorithmic/systematic trading,
  backtest, market making, HFT, execution).
- **B. Crypto / DeFi** — crypto, defi, perps, on-chain, hyperliquid, dydx.
- **C. Fleet managers / systematic operators** — prop traders, PMs, trading desks.
- **D. Academic / student pipeline** — professors/PhDs + quant/financial
  engineering; the club wedge.
- **E. Creators / streamers** — voice/influence × trading (the social catalysts).
- **F. Prop desks / allocators** — demand side (lower priority, pulled anyway).
- **AI-markets (convergence)** — ML/RL × markets (the Nof1 / Alpha Arena archetype).
- **Predictions** — Polymarket / Kalshi builders (future predictions-adapter supply).

### Scoring model
- **Floor / clean signals (score high, stand alone):**
  - Tier 1 core quant: algorithmic trading, quant, systematic, backtest, market
    making, HFT, stat arb, execution algo.
  - Tier 2 named tools (near-zero false positive): freqtrade, hummingbot,
    quantconnect, quantopian, pyfolio, alphalens, numerai, darwinex, collective2,
    crunchdao, backtrader, zipline, nautilus, vectorbt, ccxt, ib_insync/IBKR,
    MT4/MT5/MQL, pine script, tradingview, ninjatrader, tradestation, kdb+,
    bloomberg terminal, databento, polymarket, kalshi, 3commas, cryptohopper,
    quantpilot, etc.
  - Tier 3 crypto: crypto, defi, web3, on-chain, perps, hyperliquid, dydx,
    synthetix, flashbots, solana, solidity.
  - AI-markets: (reinforcement/deep/machine learning) AND (trading/markets/alpha/
    quant/crypto).
- **Firms (highest weight), current `COMPANY_NAME_ORG` + ex-employer in bio:**
  Jane Street, Jump (Trading/Crypto), Citadel Securities, Hudson River, Two Sigma,
  DRW, Optiver, Flow Traders, Tower, Virtu, Susquehanna, XTX, WorldQuant, DE Shaw,
  AQR, Man AHL, Winton, Millennium, Point72, Balyasny, Squarepoint, Capula, IMC,
  Akuna, Radix, Maven Securities, Qube, Five Rings, PDT, Voleon; crypto MM:
  Wintermute, GSR, Cumberland, Amber, B2C2, Keyrock, FalconX, DWF, Galaxy; +
  Bridgewater, **Nof1**; commodity: Vitol, Trafigura, Mercuria, Gunvor.
- **Corroboration-only (`collide`, score only with a clean hit):** brand-ambiguous
  words — GMX, Vertex, Jupiter, Drift, Mango, Maven, Kraken, Gemini, Citadel,
  Alpaca, Foundry, Composer, eToro — plus frontier labs (OpenAI, Anthropic,
  DeepMind, Mistral, Cohere, DeepSeek, Qwen, Meta AI) and competition talent
  (Kaggle, math olympiad, Putnam).
- **Markets-general (Tier 4, needs a clean hit):** trader, trading, portfolio
  manager, prop/FTMO/funded-account (kept — these are real supply, not grift),
  hedge fund, forex, options/futures trading. (FTMO/prop-challenge crowd = GOOD.)
- **Negatives (−25, bury keyword collisions):** clearly-unrelated industry in the
  org industry fields — HVAC, construction, roofing, plumbing, real estate,
  retail, restaurant/hospitality, healthcare, logistics, staffing, salon,
  automotive, etc. (mining / oil-and-gas pulled OUT — crypto-mining collision +
  commodity-trading quants are legit.)
- **Boosts:** seniority (`JOB_LEVEL_PER`), network (`LINKEDIN_CONNECTIONS_COUNT`),
  voice (publications/websites/podcast/youtube/substack), credentials (CFA/FRM/
  CQF), deliverability (`EMAIL_STATUS`=valid, phones), venture-backed, finance-app
  company.
- **Geo boosts (country-scoped so London ON ≠ London UK):** Calgary top (+20) →
  Canada local (Edmonton/Toronto/Vancouver/Montreal/Waterloo, +12) → global hubs
  (+8): NY (+ Greenwich/Stamford CT), SF Bay Area, London UK, Singapore, Hong
  Kong, Tokyo, Sydney, Dubai, Miami, Austin, Chicago, Amsterdam, Zug.
- **Haystack:** match across `about_me`, `linkedin_headline`, `skills`,
  `job_description`, title, interests, certs, education, publications, websites +
  company `about_us`/`specialties`/industry — not just job title.

### Athena pipeline
- `revenuebase.velocity` — external table over the raw gzip CSV (OpenCSVSerde,
  skip header, 173 string cols).
- `revenuebase.velocity_pq` — Parquet base (SNAPPY), nulls cleaned. One-time
  CTAS: ~24 min, ~$1.80, ~467 GB. **Built, do not rebuild.**
- `revenuebase.pf_candidates` — Stage A: cheap gate on SHORT fields only →
  survivors (gate-first because full-bio regex over 300M rows exceeds Athena's
  30-min query cap). Known trade-off: a lead whose signal is ONLY in the long bio
  is missed by the gate; Stage B still scores full bios for everyone who passes.
- `revenuebase.paperfleet_scored` — Stage B: full scoring over candidates;
  dedup on `rbid_per`; ~$0.24 per pass.
- Files in `~/`: `paperfleet_ddl.sql`, `paperfleet_candidates.sql`,
  `paperfleet_score.sql`, `paperfleet_RUNBOOK.md`.

### Status
- **BLOCKED:** AWS account suspended mid-run (ticket filed). Parquet base built;
  Stage A/B not yet run to completion. Resume per `paperfleet_RUNBOOK.md` once
  reinstated: refresh creds → Stage A → Stage B → inspect distribution.

---

## 4. Competitive / prime-lead note — Nof1 Alpha Arena

Nof1's Alpha Arena (Oct–Dec 2025): 6 frontier LLMs each given $10k to trade
crypto perps on Hyperliquid, public leaderboard, honest telemetry (excl.
unrealized P&L). ~$15M raised May 2026, NY, DeepMind/Bridgewater/Citadel alumni.
- Validates the thesis in the wild (tamper-proof scoreboard of trading agents on
  real money, same venue).
- Difference = the wedge: Alpha Arena is closed (6 models, lab-run); Paper Fleet
  is the open, crowd-supplied version (run 1000, not 6).
- The Nof1 orbit (its team, Bridgewater, AI-trading-benchmark builders) is prime
  supply — already folded into the scan as firms/convergence keywords.
