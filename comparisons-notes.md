# Paper Fleet — comparisons

Real facts (from web search) on the products Paper Fleet gets compared to, split
into what they actually are:

- **Competitors** — compete for the same user: QuantConnect, Composer, 3Commas,
  QuantPilot. Nof1/Alpha Arena is adjacent (a closed benchmark, not a consumer
  product, but nearest in thesis).
- **Blueprints** — not competitors; sources Paper Fleet borrows its shape from:
  SuitU (the game loop), pump.fun (the growth model).
- **Data source** — not a competitor: Invo (seeded Paper Fleet).

Plain notes.

## Summary (competitors only)

1. The build layer is commoditizing. QuantPilot (3Commas, 2026) already ships
   no-code/AI "describe it → backtest → run on Hyperliquid" with distribution;
   Composer has the no-code+AI builder too. The AI builder is table stakes.
2. Nobody is paper-first. Composer, 3Commas, QuantPilot all go straight to real
   money; Nof1 is real-money but closed. Paper Fleet's paper-prove-then-live on a
   shared engine is differentiated.
3. Everyone has a leaderboard; nobody has an open, un-riggable one. 3Commas =
   self-reported configs, Nof1 = honest but closed. The open, tamper-proof
   scoreboard is white space.
4. No competitor treats it as a game — collection, competition, seasons. That
   layer comes from a blueprint (SuitU), not a trading rival.

Net: against the competitors, the builder is table stakes. Paper Fleet's two
edges are the **un-riggable shared-engine record** and the **game layer** — the
first is genuinely absent from rivals; the second is adapted from SuitU (below),
with market P&L in place of votes.

---

## Competitors

### QuantConnect
- Open-source algo platform; LEAN engine (Python/C#) for research → backtest →
  live. Backtests model fees, slippage, spread, settlement. "Minimal-to-no code
  change" backtest → live. LEAN CLI; multi-asset (equities, FX, futures, crypto,
  options). Developer-first; Alpha Streams marketplace licenses strategies to funds.
- **vs Paper Fleet:** code-first for developers; PF is build-by-UI (code optional)
  with bots as persistent characters, a public leaderboard, and a
  paper-prove-then-live gate. Same core idea of one engine for backtest and live;
  PF adds the collection/competition/social layer QuantConnect has no interest in.

### Composer (composer.trade)
- No-code visual "symphonies" (drag-drop or natural-language AI). Backtests on US
  stock/ETF data, auto-executes daily via Alpaca. Users share symphonies in a
  community; thousands public.
- **vs Paper Fleet:** closest on the no-code/AI build + community sharing. Composer
  is US equities/ETFs only, goes straight to real money (Alpaca), and strategies
  are "symphonies," not characters with a record/leaderboard. PF is multi-asset,
  paper-first, and the leaderboard/track-record is the product.

### 3Commas
- Crypto trading bots since 2017: DCA, grid, options bots; connects to 20+
  exchanges via API; paper trading; a marketplace to copy top traders' bot configs.
  ~100k+ active users.
- **vs Paper Fleet:** pre-built bot *templates* you configure on your own exchange
  account (real money). Copy-marketplace records are configuration-level and not
  independently verified. PF composes arbitrary strategies, proves them on a shared
  engine, and the record is tamper-proof.

### QuantPilot (by 3Commas, 2026)
- Agentic AI crypto platform: describe a strategy in plain English → AI agents
  research, backtest, optimize, and deploy. AI research aggregates CoinMarketCap/
  DefiLlama/CryptoQuant/news. Executes on **Hyperliquid**. No-code. Nearest
  competitor.
- **vs Paper Fleet:** very close on "describe it → backtest → run on Hyperliquid"
  and the no-code AI builder. QuantPilot is crypto-only, real-money, single-user
  tooling — no persistent-character roster, no public market-judged leaderboard,
  no paper-first competition. PF is the multi-asset, gamified, leaderboard version.

### Nof1 / Alpha Arena (adjacent — benchmark, not a consumer product)
- Closed benchmark (Oct–Dec 2025): 6 frontier LLMs (GPT-5, Claude, Gemini, Grok,
  DeepSeek, Qwen) each given $10k to trade crypto perps on **Hyperliquid**, public
  leaderboard, honest telemetry (excludes unrealized P&L). ~$15M raised May 2026.
- **vs Paper Fleet:** same thesis proven in the wild — tamper-proof scoreboard of
  trading agents on real money, same venue. Difference is the wedge: Alpha Arena is
  6 lab-chosen models, closed; PF is open and crowd-supplied. A research benchmark,
  not a product you sign up for — so adjacent, not head-to-head.

---

## Blueprints (not competitors — what Paper Fleet borrows)

### SuitU (Libii) — the game loop
- Dress-up game: expressive avatar customization, plus global themed "Style
  Challenges" where thousands of users **vote** on submissions; weekly rankings;
  rewards.
- **What PF borrows:** the loop — expressive build → public arena → comparison →
  seasons → ranking. PF swaps the **subjective user vote for objective market P&L**.
  In SuitU players vote; in Paper Fleet the market votes. Challenges = seasons; the
  leaderboard = standings. This is where PF's "game layer" comes from — it isn't a
  trading invention.

### pump.fun — the growth model
- Solana memecoin launchpad: anyone makes a token in seconds (image, name, ticker)
  on a bonding curve (auto price + liquidity), instantly tradable. Fair launch — no
  presale/insider/team allocation. The market decides.
- **What PF borrows:** mass low-friction creation + market-as-judge + full
  transparency (the viral loop). Difference: pump.fun's asset is the token itself
  (pure speculation, no skill record); PF's asset is a strategy that must *earn* a
  verified record. PF = pump.fun's creation+judgment loop with a track-record spine.

---

## Data source (not a competitor)

### Invo (Involio)
- Social/copy-trading app: browse top traders with verified track records on
  leaderboards; "Mimic" to copy a trader's position (sized to your balance); earn
  when others copy you. Free app, $10 min deposit to copy. Multi-asset.
- **Relationship to PF:** this is the app whose data seeded Paper Fleet (52 top Invo
  traders, 15,713 trades mined). Invo copies *humans* placing discretionary trades;
  PF traded their *setup* (not copy-trading) and runs *strategies* (bots)
  autonomously. Invo records are verified but per-person; PF records come from one
  shared engine.

---

## Dimension table

| Product | Type | Who creates | Judged by | Assets | Money | Record |
|---|---|---|---|---|---|---|
| QuantConnect | competitor | code (Py/C#) quants | backtest + live P&L | multi-asset | real (own broker) | backtest, self-run |
| Composer | competitor | no-code / AI | backtest + live | US stocks/ETFs | real (Alpaca) | backtest, shared |
| 3Commas | competitor | no-code bot config | live P&L | crypto | real (exchange API) | marketplace, config-level |
| QuantPilot | competitor | no-code / AI agents | backtest + live | crypto (Hyperliquid) | real | backtest |
| Nof1 / Alpha Arena | adjacent | a lab (6 LLMs) | live market P&L | crypto perps (Hyperliquid) | real ($10k each) | honest, closed |
| pump.fun | blueprint | anyone (a token) | the market (bonding curve) | the token itself | real | price only, no skill record |
| SuitU | blueprint | anyone (an outfit) | **user votes** | n/a (game) | virtual | competition rankings |
| Invo | data source | human traders | live P&L | multi-asset | real ($10 min, copy) | verified, per-person |
| **Paper Fleet** | — | anyone (code or no-code/AI) | **live market P&L** | multi-asset (crypto live; equities/futures built; predictions added) | **paper-first → real on explicit switch** | **same engine tests & trades (un-riggable)** |

## Where Paper Fleet sits

- **Build layer** overlaps the competitors (Composer/QuantPilot no-code+AI,
  QuantConnect one-engine). This is the commoditizing part.
- **Judge is the live market**, like the competitors' live P&L; the idea of the
  market itself judging mass creation is pump.fun's (blueprint), not user votes.
- **Game loop** is adapted from SuitU (blueprint) — expressive build → arena →
  seasons — with market P&L replacing the vote. No competitor has this.
- **Money model** is paper-first then an explicit switch to live — unlike every
  competitor (straight to real money) and unlike Nof1 (real-money, lab-only).
- **Record** is the differentiator vs competitors: one engine tests and trades, so
  the leaderboard can't be gamed — unlike 3Commas (self-reported) or Invo
  (per-person; and Invo is the data source, not a rival).
- **Built on:** Invo's data seeded the origin strategy.

## Sources

- QuantConnect: [LEAN (GitHub)](https://github.com/quantconnect/lean), [docs — algorithm engine](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine)
- Composer: [Alpaca writeup](https://alpaca.markets/blog/how-composer-is-redefining-algorithmic-trading-with-their-no-code-platform/), [Trade with AI](https://help.composer.trade/article/254-what-is-trade-with-ai)
- 3Commas: [review](https://www.daytrading.com/3commas), [algoplatforms](https://algoplatforms.com/platforms/3commas)
- QuantPilot: [3Commas launch (OpenPR)](https://www.openpr.com/news/4453236/3commas-launches-quantpilot-the-agentic-ai-platform-built), [Crypto Daily](https://cryptodaily.co.uk/2026/04/3commas-unveils-quantpilot-targeting-retail-traders-with-institutional-style-ai-tools)
- pump.fun: [DappRadar guide](https://dappradar.com/blog/ultimate-guide-to-pump-fun-the-leading-memecoin-launchpad), [Forbes](https://www.forbes.com/sites/digital-assets/article/what-is-pumpfun/)
- SuitU: [App Store](https://apps.apple.com/us/app/suitu-fashion-avatar-dress-up/id1663749627), [SuitU Wiki](https://suitudressup.fandom.com/wiki/SuitU_Wiki)
- Invo: [tradeinvo.com](https://www.tradeinvo.com/), [App Store](https://apps.apple.com/in/app/invo-where-traders-are-made/id1601301148)
- Nof1 / Alpha Arena: [bitcoin.com](https://news.bitcoin.com/6-bots-with-real-money-hyperliquid-hosts-first-ever-ai-trading-showdown/), [SCMP](https://www.scmp.com/tech/tech-trends/article/3329784/deepseek-outperforms-ai-rivals-real-money-real-market-crypto-showdown)
