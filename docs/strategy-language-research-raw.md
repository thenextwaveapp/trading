# Strategy-language research — raw agent reports

Collected 2026-11-04. Four parallel research agents, reports reproduced verbatim below.
Purpose: ground a universal strategy-import pipeline (many languages → our JSON condition-tree DSL).

- [Report 1 — QuantScript disambiguation](#report-1--quantscript)
- [Report 2 — Pine Script (v5/v6) deep dive](#report-2--pine-script-v5v6)
- [Report 3 — MQL4/5, EasyLanguage, thinkScript (+ NinjaScript, AFL)](#report-3--mql45-easylanguage-thinkscript--ninjascript-afl)
- [Report 4 — Declarative formats: Composer, no-code builders, webhooks, MCP](#report-4--declarative--no-code-formats)

---

# Report 1 — QuantScript

**Bottom line:** There is no single established "QuantScript." The name is contested across at least five distinct things, all obscure or very new (2024–2026 era). Two matter: **(1) the open-source QuantScript language/SDK** at quantscript.org (owns the name, domains, npm package, and public spec) and **(2) 3Commas QuantPilot's internal "QuantScript"** (biggest commercial backing, launched mid-2026, but closed and undocumented publicly). Neither has meaningful adoption yet. The rest are academic toy compilers, a dead Google Code project, and name-collision red herrings.

## Candidate 1: QuantScript (quantscript.org / quantscript.com / GilgameshSG) — the "canonical" one

- **Who/what:** Open-source trading DSL + SDK by **Gilgamesh Pte. Ltd. (Singapore)**, Apache-2.0, copyright 2025–2026. The commercial front (quantscript.com) is a visual platform "in partnership with DemoTrader.net" — playground, strategy leaderboard ("Strategy Arena"), cloud deploy; parts marked "coming soon." Distributed on npm as `@quantscript/lang`.
- **Popularity:** Tiny and brand new. GitHub repo: **12 stars, 0 forks, ~14 commits**. No measurable community. But it holds the name: quantscript.org, quantscript.com, the `.qs` extension, full public docs/spec.
- **Language shape:** **Declarative–imperative hybrid, JavaScript/TypeScript-like syntax.** Declarative header (mode, broker, data, risk) + imperative event handlers:
  ```js
  mode(mode_type: "backtest", script_name: "BasicMeanReversion");
  broker(adapter: "sim", config: { initial_capital: 100000, spread: 25 });
  candles(adapter: "parquet", symbol: "XAUUSD", resolution_type: "15m");
  event.onCandle((candle) => {
    let rsi = ta.rsi(close, 14);
    if (rsi < 30) { trade.buy({...}); }
  });
  ```
- **Constructs:** 50+ indicators via `ta.*` (SMA/EMA/RSI/ATR/ADX/MACD/Bollinger/Supertrend), `trade.*` order API, first-class `risk.*` namespace (SL/TP, position limits, circuit breakers), multi-dataset/multi-timeframe via `data.loadCandles()`, variables, conditionals, state, and presumably JS-style loops/functions. Events: `onCandle`, `onTick`, `onTimer`, broker lifecycle.
- **Execution model:** Event-driven, supporting both **bar-by-bar (Pine-style) and tick-level (MQL-style)**. Four modes from one script: indicator / backtest / forwardtest / live.
- **Determinism/repainting:** Explicitly markets "deterministic historical simulation" and "explicit time semantics" around candle completion and lookahead; JSONL "Run Journals" for reproducibility.
- **Portability:** `.qs` files are plain text with a spec "independent of a particular UI, broker, data vendor, or cloud provider"; backtests export JSONL journals + Markdown reports.
- **Translatability to your JSON condition-tree DSL:** **Good for the idiomatic subset, partial overall.** Crucially, their docs promote a **"Declarative Signals" pattern** as the recommended architecture — stateless named boolean signals ("no flags, no counters, no memory") plus a mechanical signal→order mapping:
  ```js
  const trendUp   = htf.mom > 0 && close > htf.sma;
  const longEntry = ta.crossover(close, sma) && trendUp && calmRegime;
  ```
  Strategies written this way map almost 1:1 onto your indicator-comparison + AND/OR/NOT + entry/exit/stop/sizing model. But the language *permits* arbitrary imperative state, counters, grid logic (e.g., their Mean Reversion Grid example), and tick handlers — those won't translate. You'd translate the declarative-signals subset and reject/flag the rest.
- **Sources:** https://github.com/GilgameshSG/quantscript · https://quantscript.org/ · https://www.quantscript.org/about · https://www.quantscript.org/examples · https://www.quantscript.com/

## Candidate 2: QuantScript (3Commas QuantPilot) — biggest commercial backing

- **Who/what:** The internal strategy language of **QuantPilot**, 3Commas' agentic AI crypto-trading platform (announced April 2026, public launch June 17, 2026). AI agents translate plain-English strategy descriptions into QuantScript; users read/inspect the generated code but don't write it. 5,000+ traders in beta; pricing TBD (token-credit system).
- **Language shape:** Conflicting reports — reviews call it **"Python-based,"** but the only circulating example looks like a custom declarative DSL:
  ```
  // QuantScript v0.2
  asset BTC.USD
  timeframe 1W
  source price = close(exchange="Binance")
  opt macd_sweep {
    param fast in 6..24
    param slow in 12..52 where slow > fast
    macdLine = ta.macd(price, fast, slow, 9).line
    enter long when crossup(macdLine, macdSig)
    exit  long when crossdown(macdLine, macdSig)
  }
  ```
  Likely a declarative DSL executed by a Python engine. No public grammar, docs, or spec.
- **Constructs:** asset/timeframe/source declarations, `ta.*` indicators, parameter sweep blocks with constraints (`param fast in 6..24 where slow > fast`), `enter/exit <side> when <condition>`, risk parameters, even on-chain data sources (`yield.estimate`). No evidence of loops or user state.
- **Execution model:** **Bar-by-bar**, deterministic backtests in QuantPilot's own engine on 1-minute candles, modeling real Hyperliquid order-book liquidity. Live execution gated on a Hyperliquid integration.
- **Portability:** **Closed.** Runs only inside QuantPilot; no export format documented.
- **Translatability:** **Excellent structurally** — `enter long when <boolean expr over indicators>` is essentially already your condition-tree model, plus entry/exit/risk blocks. The obstacle is access, not shape: no public spec, closed ecosystem, and the "Python-based" ambiguity. If you ever ingest it, the visible surface maps cleanly; parameter-sweep (`opt`) blocks have no equivalent in a pure condition tree and would need flattening to chosen values.
- **Sources:** https://www.quantpilot.ai/ · https://3commas.io/blog/quantpilot-is-now-live · https://finestel.com/blog/quantpilot-review/ · https://aitoolblaze.com/blog/quantpilot-review-2026 · https://www.globenewswire.com/news-release/2026/04/02/3267686/0/en/3commas-launches-quantpilot-the-agentic-ai-platform-built-for-the-next-generation-of-crypto-traders.html

## Candidate 3: SHIVAMCP18/QuantScript — academic unit-checked compiler

- **Who/what:** Personal/academic project; DSL that **compiles to optimized C++17**. 0 stars, 0 forks, 4 commits.
- **Shape/constructs:** Typed declarative-ish DSL: `const`/`param`/`state` declarations with **units of measure** (price/volume/scalar dimensional checking), `series` window ops (mean, std, highest, lowest) optimized to O(1), event handlers `on bar_close` / `on bar_open`, orders via `buy`/`sell`/`flatten`.
- **Notable:** **Compile-time rejection of look-ahead bias** (causality checking) — directly relevant to your determinism concerns. Compiles via three-address code + graph-coloring register allocation to a self-contained C++ class with backtest harness; TAC interpreter for differential testing.
- **Execution:** Bar-event-driven over CSV bars; `.qs` in, `.hpp`/`.cpp` out.
- **Translatability:** Moderate — entries/exits and indicator windows map, but `state` variables don't. Irrelevant in practice (zero adoption), though its causality-checking design is worth reading as prior art.
- **Source:** https://github.com/SHIVAMCP18/QuantScript

## Candidate 4: CppCracker11/QuantScript — undergrad compiler project

Undergraduate Compiler Design class project; DSL compiler for trading rules. 0 stars, 6 commits, **no README or docs visible**. Ignore.
- **Source:** https://github.com/CppCracker11/QuantScript

## Candidate 5: ivannp/quantscript — dead legacy project (not a language)

Ivan Popivanov's old Google Code export: Python/R **pipeline scripts** (EODData FTP download → SQLite → R analysis → email), 14 stars, 6 forks, abandoned by the author. **Not a strategy language at all.** Zero translation relevance.
- **Source:** https://github.com/ivannp/quantscript

## Red herrings (same/similar name, unrelated)

- **QuantScripts.io** — SaaS that batch-backtests **Pine Script** across 100+ tickers; there is no "QuantScript language" here. (https://www.quantscripts.io/)
- **testaryan123/Quantscript** — AI pipeline generating finance-education *video scripts* (Next.js + Claude). Unrelated. (https://github.com/testaryan123/Quantscript)
- **redx94/QuantaScript** — quantum-computing language. Unrelated. (https://github.com/redx94/QuantaScript)
- Not associated with QuantConnect (which uses LEAN/C#/Python), Quantower, or TradingView.

## Verdict for your pipeline

No QuantScript is prominent enough today to prioritize as a translation source. If forced to rank: **QuantPilot's QuantScript** has the most users behind it but is closed and spec-less; **quantscript.org (Gilgamesh)** is the one you could actually build a parser against — open Apache-2.0 spec, `.qs` plain-text format, and its officially recommended "Declarative Signals" idiom is nearly isomorphic to your JSON condition-tree DSL (named boolean signals over `ta.*` comparisons → AND/OR groups; mechanical signal→order mapping → entry/exit blocks; `risk.*` → stop/sizing). The practical approach for both: support the declarative subset (indicator comparisons, crossovers, boolean composition, SL/TP/sizing params) and reject scripts using tick handlers, counters, grid state, or loops.

Sources: [quantscript.org](https://quantscript.org/) · [quantscript.org/about](https://www.quantscript.org/about) · [quantscript.org/examples](https://www.quantscript.org/examples) · [quantscript.com](https://www.quantscript.com/) · [GilgameshSG/quantscript](https://github.com/GilgameshSG/quantscript) · [QuantPilot](https://www.quantpilot.ai/) · [3Commas launch post](https://3commas.io/blog/quantpilot-is-now-live) · [GlobeNewswire launch PR](https://www.globenewswire.com/news-release/2026/04/02/3267686/0/en/3commas-launches-quantpilot-the-agentic-ai-platform-built-for-the-next-generation-of-crypto-traders.html) · [Finestel QuantPilot review](https://finestel.com/blog/quantpilot-review/) · [aitoolblaze review](https://aitoolblaze.com/blog/quantpilot-review-2026) · [SHIVAMCP18/QuantScript](https://github.com/SHIVAMCP18/QuantScript) · [CppCracker11/QuantScript](https://github.com/CppCracker11/QuantScript) · [ivannp/quantscript](https://github.com/ivannp/quantscript) · [quantscripts.io](https://www.quantscripts.io/) · [testaryan123/Quantscript](https://github.com/testaryan123/Quantscript/blob/main/quantscript_documentation.md)

---

# Report 2 — Pine Script (v5/v6)

# Pine Script (v5/v6) → Declarative JSON DSL: Translation-Oriented Research Report

## 1. Execution model (mechanical)

Source: https://www.tradingview.com/pine-script-docs/language/execution-model/

**Bar-by-bar series model.** A Pine script's global scope executes exactly once per historical bar, left to right (oldest → newest). Before each execution the runtime loads that bar's confirmed OHLCV into `open/high/low/close/volume`; after execution it **commits** all series values for that bar into the time series. The history operator `x[n]` reads the *committed* value from n bars back — never the in-progress value. Historical buffers default to auto-sizing, max 5000 bars for most series (`max_bars_back`).

**Variable declaration modes** (the whole "state" story reduces to this):
- no keyword: re-declared/re-initialized on *every* bar (pure, stateless per-bar binding)
- `var`: initialized once on the first bar; mutations persist bar-to-bar; value is rolled back to last committed state on each realtime tick
- `varip` ("intrabar persist"): survives rollback — persists across *ticks* within a realtime bar. Cannot be reproduced on historical bars (no tick data), so it is intrinsically repainting.

**History vs realtime bars.** On historical bars: one execution per bar on final data. On the realtime (open) bar, an *indicator* re-executes on every tick; before each re-execution the engine performs a **rollback**: all non-`varip` variables, `var` state, and plots are reset to the last committed state, then recomputed from the new tick values. Only the execution on the bar's closing tick is committed. Things that are NOT rolled back: `varip` values, strategy order fills, logs. Consequence: `x[1]` during realtime always means "value committed at close of previous bar," which matches your DSL's `offset` semantics exactly.

**Strategies differ from indicators**: by default a strategy executes once per bar *at bar close* even on realtime bars (`calc_on_every_tick=false` default). So a plain-vanilla Pine strategy is already a deterministic bar-close evaluator — the same model as your DSL. Modifiers that break this: `calc_on_every_tick=true` (per-tick execution; Premium+), `calc_on_order_fills=true` (extra executions at fill moments, giving the script access to mid-bar equity — not representable in bar-close DSL), `calc_on_every_history_tick`.

**barstate** namespace: `barstate.ishistory` (bar was closed when script loaded), `barstate.isrealtime`, `barstate.isconfirmed` (current execution is on the bar's final/closing update — on historical bars always true), `barstate.isnew` (first tick of a bar — fires at bar open in realtime but effectively at bar close on historical bars, so it repaints), `barstate.islast`, `barstate.islastconfirmedhistory`.

**Repainting, mechanically** (source: https://www.tradingview.com/pine-script-docs/concepts/repainting/): defined as "script behavior causing historical vs realtime calculations or plots to behave differently." Docs estimate >95% of indicators repaint in some form. Mechanism classes:
1. **Fluid values**: using realtime `high/low/close` before confirmation — recalculates per tick, then the committed value differs from what was shown intrabar. Eliminated by bar-close evaluation (your model) or `barstate.isconfirmed` / `[1]` offsets.
2. **Future leak**: `request.security(sym, tf, expr, lookahead=barmerge.lookahead_on)` *without* offsetting `expr` lets historical bars read the HTF bar's close before it existed. Prohibited in published scripts. The canonical **non-repainting HTF pattern** is `request.security(sym, tf, expr[1], lookahead=barmerge.lookahead_on)` — the `[1]` and `lookahead_on` are a matched pair: it returns the last *confirmed* HTF value, consistently on both historical and realtime bars. Translation rule: your multi-timeframe operand refs should bind to "last closed HTF bar" = exactly this pattern; a Pine script using raw `request.security(..., close)` (no offset, lookahead_off) gives unconfirmed HTF values on realtime bars and confirmed ones historically — translate it to last-closed-HTF semantics and document the (desirable) behavior change.
3. **`varip`**, **`calc_on_every_tick`**, **`timenow`**, `barstate.isnew` — tick-dependent, unreproducible historically → untranslatable to deterministic bar-close; reject or degrade with warning.
4. **Offset/pivot plotting** (`ta.pivothigh` plotted with negative offset): visual-only repainting; the underlying *signal timing* (confirmed `rightbars` later) is deterministic and translatable.
5. Dataset-start variance: calculations seeded from the first chart bar (EMA seeds, `var` init) shift when history depth changes — relevant to matching TradingView numbers in verification: you must replicate the warm-up window.

## 2. strategy.* API surface

Sources: https://www.tradingview.com/pine-script-docs/concepts/strategies/ and reference https://www.tradingview.com/pine-script-reference/v6/

**Order functions:**
- `strategy.entry(id, direction, qty, limit, stop, oca_name, oca_type, comment, alert_message)` — market order unless `limit`/`stop` given (both → stop-limit). Auto-reverses: an opposite-direction entry closes the existing position AND opens the new one (fill size = |position| + qty). Respects `pyramiding` (declaration param, default 1 = one open entry per position).
- `strategy.order(...)` — raw order, no reversal logic, ignores pyramiding. Rarely maps to a declarative DSL; treat as red flag.
- `strategy.close(id, qty/qty_percent)` / `strategy.close_all()` — market close.
- `strategy.exit(id, from_entry, qty, qty_percent, profit, loss, stop, limit, trail_price, trail_points, trail_offset, oca_name, comment...)` — bracket orders:
  - `stop` / `limit`: **absolute prices** (stop-loss / take-profit)
  - `loss` / `profit`: **relative distances in ticks** (syminfo.mintick units) from entry price
  - trailing: needs an activation (`trail_price` absolute price OR `trail_points` ticks from entry) plus `trail_offset` (ticks the stop trails behind best price). Trail updates intrabar in the broker emulator.
  - If both absolute and relative forms given, v6 uses whichever triggers first (v5 prioritized absolute).
  - stop+limit together form an OCA bracket (first touch wins, other cancels; default `strategy.oca.reduce`).
  - `qty/qty_percent` *reserves* part of the position for that exit; multiple exit calls layer.
- `strategy.cancel`/`cancel_all`.

**Fill model (broker emulator):** orders created during bar N's execution fill earliest at bar N+1's **open** (market orders), or intrabar when price touches stop/limit levels. Intrabar path assumption from OHLC: open→high→low→close if open is nearer the high, else open→low→high→close; no intrabar gaps assumed (any price within range is reachable); gap-through orders fill at next open. `use_bar_magnifier=true` (Premium+) substitutes real lower-TF data for the path. `process_orders_on_close=true` shifts market-order fills to the *close of the signal bar* instead of next open.

**Declaration params relevant to sizing/exits:** `default_qty_type` ∈ {`strategy.fixed` (contracts/shares), `strategy.cash` (currency notional), `strategy.percent_of_equity`}, with `default_qty_value`; `initial_capital`; `currency`; `commission_type/value`; `slippage` (ticks); `margin_long/margin_short` (v6 default 100); `close_entries_rule` ("FIFO" default, "ANY"); `pyramiding`.

**Mapping to your DSL:**
- Maps cleanly: `stop`/`loss` → stop modes (absolute price vs tick/percent distance — note Pine's relative form is in *ticks*, so you need mintick metadata to convert to %); `limit`/`profit` → take_profit; `trail_points`+`trail_offset` → trailing; `percent_of_equity` → risk-fraction-ish sizing (caveat: it's % of *current equity* as notional, not risk-per-trade; `strategy.cash` → notional cap; `strategy.fixed` → fixed qty); `process_orders_on_close=true` → your deterministic close-fill model. `pyramiding=1` + entry/exit pairs → single-position DSL.
- Time-based exit (`time_bars`): Pine has **no built-in**; the idiom is `if bar_index - strategy.opentrades.entry_bar_index(0) >= N` (or `ta.barssince(entryCond)`) → `strategy.close`. Your translator should pattern-match this idiom.
- Does NOT map / divergence sources: intrabar stop/limit fills (your bar-close engine will fill stops at next close or with OHLC-touch approximation — expect P&L divergence vs TradingView unless you model touch-fills); trailing stops (updated intrabar along the emulated path — bar-close trailing is systematically looser); `calc_on_order_fills`; `calc_on_every_tick`; OCA custom groups; partial/multi-level exits via layered `strategy.exit` qty reservations; margin/FIFO nuances; `strategy.order`; dynamic qty expressions computed from `strategy.equity`/`strategy.position_avg_price` mid-script (common idiom for risk-based sizing: `qty = (equity * risk%) / (entry - stop)` — this *is* your risk-fraction mode; pattern-match it).
- Default fill-at-next-open is the single biggest reconciliation issue: a Pine signal on bar N fills at open(N+1). If your DSL fills at close(N), trade prices differ by one open-close gap per trade. Either fill at next open in your engine or require `process_orders_on_close` semantics when verifying.

## 3. ta.* built-ins: stateful vs pure-windowed

Reference: https://www.tradingview.com/pine-script-reference/v6/ (ta namespace)

Most-used (by observation of the public library): `ta.sma, ta.ema, ta.rma, ta.wma, ta.vwma, ta.hma, ta.rsi, ta.macd, ta.stoch, ta.atr, ta.tr, ta.bb, ta.bbw, ta.kc, ta.cci, ta.mfi, ta.mom, ta.roc, ta.cmo, ta.dmi/ta.adx, ta.sar, ta.supertrend, ta.vwap, ta.obv, ta.cum, ta.change, ta.cross, ta.crossover, ta.crossunder, ta.highest, ta.lowest, ta.highestbars, ta.lowestbars, ta.stdev, ta.variance, ta.correlation, ta.linreg, ta.percentile_nearest_rank, ta.median, ta.rising, ta.falling, ta.barssince, ta.valuewhen, ta.pivothigh, ta.pivotlow, ta.alma, ta.wpr, ta.tsi, ta.cog`.

**Pure windowed (recomputable from the last N bars — trivially safe for your DSL):** sma, wma, alma, swma, highest/lowest(+bars), stdev, variance, linreg, mom, roc, change, median, percentile_*, cog, correlation, stoch, wpr, cci (window), mfi, bb/bbw (sma+stdev), vwma.

**Recursive/stateful (infinite impulse response — value depends on the entire history since bar 0):** `ta.ema` (alpha=2/(len+1)), `ta.rma` (alpha=1/len; used inside **rsi, atr, adx/dmi**), `ta.sar`, `ta.supertrend` (direction latch), `ta.tsi` (double EMA), `ta.macd` (EMAs), `ta.cum`, `ta.obv`, `ta.vwap` (anchored — resets per session/anchor). **Seeding:** ema/rma return `na` for the first `length-1` bars and seed their first value with the SMA of the first `length` values; thereafter purely recursive. Mechanical consequence for verification: an EMA-based strategy's early trades depend on where history starts; replicate the SMA seed and allow a warm-up convergence window (EMA/RMA converge geometrically; ~4×length bars gets you within float noise). `na` inputs: ta functions generally carry the last state without advancing.

**Event-memory functions (unbounded lookback, need a latch in your engine, not a window):**
- `ta.barssince(cond)`: bars since cond was last true; `na` before first occurrence. Equivalent to a counter reset on cond — representable as derived state, or usable for your `time_bars` exit detection.
- `ta.valuewhen(cond, source, occurrence)`: value of `source` on the Nth-most-recent bar where cond was true. occurrence=0 = "sticky last value on event" — representable as a sample-and-hold operand; occurrence≥1 needs a small ring buffer.
- `ta.pivothigh(src, left, right)` / `pivotlow`: returns the pivot *price* on the bar where confirmation completes, i.e. `right` bars *after* the pivot bar; `na` otherwise. Deterministic and non-repainting at signal level (the lag is intrinsic); commonly fed into `ta.valuewhen`/`fixnan` for S/R levels.
- `ta.cross/crossover/crossunder`: `crossover(a,b)` ≡ `a > b and a[1] <= b[1]` — exactly expressible in your condition tree with offset=1.

**Critical execution constraint:** every `ta.*` call site maintains its own internal series state and **must execute on every bar**; calling ta functions inside conditional branches yields inconsistent history (compiler warning). Translation implication: hoist all indicator computations to unconditional per-bar evaluation (which your DSL already does by construction) — any Pine script that *deliberately* gates a ta call inside an `if` for conditional sampling is relying on execution-skipping semantics you can't express.

## 4. Construct frequency in public scripts

No official TradingView statistics exist on construct frequency; treat all numbers here as estimates. Evidence available:
- The **pyne-in-the-wild** corpus (https://github.com/PyneSys/pyne-in-the-wild, from the PyneCore Pine-to-Python project) is the only public reproducible corpus of real published open-source Pine scripts (manifest with author/license/version/kind/SHA-256; sources not redistributed). Search results reference ~309 open-corpus strategies + 741 closed-test scripts graded against TradingView's own trade lists — useful both as a prevalence sample and as a ready-made verification methodology (grade your translator's trade list against TV's export).
- Qualitative consensus (PineCoders FAQ https://www.pinecoders.com/faq_and_code/, docs): `var` is extremely common (ubiquitous for trade-level state, flags, counters — any script tracking "entry price" or "bars in trade" uses it); `varip` is rare (realtime/tick tooling only); explicit `for`/`while` loops and arrays are common in *indicators* (tables, screeners, ML-style scripts) but a large share of *strategies* — the classic MA-cross / RSI / breakout / supertrend family that dominates popularity rankings — use no loops, no arrays, and only implicit state inside ta.* calls plus optionally `var` for trade management. Realistic planning numbers: expect roughly half of public strategies to be fully expressible in a loop-free, var-free condition-tree + exit-block DSL; expect most of the remainder to use `var` only in patterns you can pattern-match (entry-price latch, barssince-style counters, trailing-level tracking — all representable as your exit block's built-in state). Scripts with arrays/matrices/loops/UDTs are a long tail you should detect and reject early. These proportions are estimates, not measured data.

## 5. Pine v6 changes relevant to translation

Source: https://www.tradingview.com/pine-script-docs/migration-guides/to-pine-version-6/ (v6 GA Dec 2024)

- **Dynamic requests default-on**: all `request.*()` can take series symbol/timeframe args, run in local scopes, and vary per bar. Translation impact: you can no longer assume the MTF operand set is statically known from the source — restrict support to `request.security` calls with const/input symbol+timeframe args; reject series args.
- **bool**: no implicit int/float→bool; **bool can never be `na`** (na/nz/fixnan reject bool). Simplifies your condition-tree semantics (ternary logic only enters via na *numeric* comparisons, which Pine defines as false-ish comparisons returning na → your evaluator should treat comparisons involving na as false to match).
- **`and`/`or` are now lazy** (short-circuit) — matters only for side-effectful operands (function calls with state inside conditions); in v5 both sides always executed, keeping ta-call histories consistent. A v5 script relying on strict evaluation of a ta call inside a condition changes behavior under v6 — and under your evaluator; hoist all indicator subexpressions unconditionally.
- `strategy.exit` now triggers on whichever of absolute (stop/limit) vs relative (loss/profit) hits first (v5: absolute priority).
- `when` parameter removed from strategy.* (v5 scripts using `when=` → fold into an `if`).
- `margin_long/short` default 100 (was 0) — affects fills when equity insufficient; order count >9000 trimmed not errored.
- Negative array indices; `[]` not allowed on literals or directly on UDT fields (`(obj[10]).field`); const int division now fractional; `timeframe.period` always includes multiplier ("1D" not "D"); `offset` in plots no longer series; dynamic for-loop bounds.

## 6. Export & verification

- **Export**: Strategy Tester → "List of Trades" and "Performance Summary" tabs each export separately (CSV; newer UI also offers XLSX). The CSV always contains *all* columns regardless of the UI column setup. Columns of List of Trades: **Trade #** (sequential, both rows of a trade share it), **Type** ("Entry long"/"Exit long"/"Entry short"/"Exit short" — each trade = entry row + exit row pair), **Signal** (the `id`/comment string passed to strategy.entry/exit/close — carry your DSL rule ids through to match), **Date/Time** (chart's timezone, "YYYY-MM-DD HH:MM" style; note timezone is the *chart* setting, usually exchange time — normalize before diffing), **Price**, **Quantity/Position size** (contracts and value), **P&L** (absolute + %), **Run-up** (max favorable excursion, abs+%), **Drawdown** (max adverse excursion, abs+%), **Cumulative P&L** (abs+%). Sources: https://www.tradingview.com/support/solutions/43000613680-how-to-export-strategy-data/, https://www.tradingview.com/support/solutions/43000681737-list-of-trades-tab/ and the per-column pages (…43000681738 Trade #, …43000681739 Type, …43000681740 Signal, …43000681742 Date and time). Verification caveats: Run-up/Drawdown are computed from intrabar extremes (bar magnifier-dependent), so don't diff those tightly; diff entry/exit timestamps, prices, direction, qty, and P&L. Standard trade list keeps the most recent **9000 trades** (strategy.* accessor functions likewise limited to latest 9000).
- **Deep Backtesting** (https://www.tradingview.com/support/solutions/43000666265-how-deep-backtesting-works/, …43000668210): Premium+ only. Lets you backtest a chosen date range over all available history instead of only chart-loaded bars (standard chart ≈ 20k bars on Premium). Caps: **2,000,000 bars and 1,000,000 trades** per calculation (older range beyond 2M bars is truncated to most recent 2M). Results appear only in the Strategy Tester report — no chart plots/markers. Daily+ timeframes use full history; intraday history is shorter. Export works from Deep Backtesting results, making it the best source of long verification trade lists.

## 7. Licensing / ToS posture

- **Default license**: "All open-source scripts on TradingView use the Mozilla Public License 2.0 by default"; authors may substitute another license in the source header. Source: https://www.tradingview.com/pine-script-docs/writing/publishing/
- **Visibility tiers**: open-source (code visible), protected (closed, paid plans), invite-only (closed + access-gated, Premium+, monetizable). Privacy (public/private) is immutable after publication.
- **Users' own scripts**: users retain ownership of content they create (TradingView ToS grants TV a license to host/display; it does not transfer ownership — https://www.tradingview.com/policies/). A user porting *their own* Pine scripts (private or published) into your DSL is legally unproblematic; your translator ingesting a user's own source is the clean case to build the product around.
- **Third-party open-source scripts**: off-platform, MPL 2.0 governs — it's file-level copyleft: you may use, modify, translate; if you *distribute* the covered/modified code (arguably including a mechanical translation, which is a derivative work) those portions must remain MPL-licensed with notices preserved, but MPL does not virally infect your whole platform (unlike GPL), and merely *running* a translated script server-side without distributing it triggers no MPL distribution obligations. Watch for author headers overriding MPL or forbidding reuse (the pyne-in-the-wild corpus explicitly filters these out — a sensible policy to copy).
- **On-platform rules ≠ license**: TradingView's Script Publishing Rules (https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/) state their "open-source reuse" criteria (credit author, meaningful improvement, republish open-source) "take precedence over any provisions from an open-source license" — but these govern publishing *on TradingView* only; they don't restrict off-platform use beyond the MPL.
- **Protected/invite-only scripts**: no source access; circumventing (decompiling, scraping) violates ToS. Your translator should only accept pasted source the user possesses — don't fetch from TradingView.

**Top translation decisions this research supports**: (a) model fills at next-bar open (or require process_orders_on_close parity) before diffing against List-of-Trades exports; (b) implement SMA-seeded EMA/RMA with warm-up handling to match TV numbers; (c) bind MTF refs to confirmed-HTF-bar semantics (`expr[1]` + lookahead_on equivalence); (d) convert Pine tick-denominated exit distances via syminfo.mintick; (e) pattern-match the small set of `var` idioms (entry-price latch, barssince counter, trailing level) instead of supporting general mutable state; (f) hard-reject varip, calc_on_every_tick, calc_on_order_fills, strategy.order, series-arg request.security, loops/arrays — each is either nondeterministic under bar-close evaluation or outside declarative expressiveness.

Key source URLs: https://www.tradingview.com/pine-script-docs/language/execution-model/ · https://www.tradingview.com/pine-script-docs/concepts/repainting/ · https://www.tradingview.com/pine-script-docs/concepts/strategies/ · https://www.tradingview.com/pine-script-reference/v6/ · https://www.tradingview.com/pine-script-docs/migration-guides/to-pine-version-6/ · https://www.tradingview.com/support/solutions/43000613680-how-to-export-strategy-data/ · https://www.tradingview.com/support/solutions/43000666265-how-deep-backtesting-works/ · https://www.tradingview.com/support/solutions/43000668210-how-much-data-is-available-for-deep-backtesting/ · https://www.tradingview.com/pine-script-docs/writing/publishing/ · https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/ · https://www.pinecoders.com/faq_and_code/ · https://github.com/PyneSys/pyne-in-the-wild

Flagged lower-confidence items: exact export timestamp format/timezone (chart-timezone, verify against a live export); the one-row-vs-two-row CSV trade structure has varied across UI versions; section 4 percentages are estimates — the pyne-in-the-wild manifest is the best path to measured numbers.

---

# Report 3 — MQL4/5, EasyLanguage, thinkScript (+ NinjaScript, AFL)

Target DSL assumed: declarative JSON condition tree (indicator comparisons, AND/OR/NOT, bar offsets, exit block = stop/TP/trailing, sizing block; no loops/state; deterministic bar-close evaluation)

## A) MQL4 / MQL5 (MetaTrader 4 / 5)

### A1. EA structure — construct-level mechanics

Event model: an Expert Advisor is an event-driven C-like program (MQL4 ≈ C, MQL5 ≈ C++ subset with classes). Mandatory/typical handlers:
- OnInit() — runs once at attach; MQL5 EAs create indicator HANDLES here (int h = iMA(symbol, period, maPeriod, shift, MODE_SMA, PRICE_CLOSE)). Returns INIT_SUCCEEDED/INIT_FAILED.
- OnTick() — fired on every incoming quote (NewTick event). All trading logic lives here. There is no built-in "on bar close" event; EAs emulate it with a static datetime lastBarTime guard comparing iTime(...,0) / time[0].
- OnDeinit(const int reason) — cleanup, limited to 2.5 s.
- Optional: OnTimer(), OnTrade(), OnTradeTransaction(), OnChartEvent(), OnTester() (custom optimization criterion).
Sources: https://docs.mql4.com/basis/function/events , https://www.mql5.com/en/docs/runtime/testing

Indicator access — the critical MQL4/MQL5 split:
- MQL4: indicator functions return values directly with an inline bar-shift argument: iMA(Symbol(), 0, 14, 0, MODE_SMA, PRICE_CLOSE, 1) = SMA(14) on bar index 1 (last closed bar). This maps 1:1 to your DSL's {indicator, params, offset} leaf. Same pattern for iRSI, iMACD(+mode for signal/main line), iStochastic, iBands, iATR, iCustom.
- MQL5: two-phase. OnInit creates a handle (int h = iRSI(...)); OnTick pulls values via CopyBuffer(h, bufferIndex, startPos, count, array) into a double[] with ArraySetAsSeries. Buffer index selects the line (e.g. MACD main=0, signal=1). Mechanically noisier but still statically analyzable: handle creation gives you the indicator+params, CopyBuffer start position gives you the bar offset.
Sources: https://www.mql5.com/en/articles/31 , https://docs.mql4.com/trading/ordersend

Order execution:
- MQL4: int ticket = OrderSend(symbol, cmd /*OP_BUY, OP_SELL, OP_BUYLIMIT, OP_SELLLIMIT, OP_BUYSTOP, OP_SELLSTOP*/, lots, price, slippage, stoploss, takeprofit, comment, magic, expiration, color). SL/TP are absolute prices attached at send time. Position state is queried by iterating OrdersTotal()/OrderSelect() filtered by magic number — the magic number IS the EA's position-state mechanism. Modification via OrderModify (this is how trailing stops are implemented: recompute SL each tick and OrderModify).
- MQL5: netting/hedging position model; raw OrderSend(MqlTradeRequest&, MqlTradeResult&) struct call, but nearly all modern code uses the Standard Library CTrade class: trade.Buy(lots, symbol, price, sl, tp), trade.PositionModify(), plus CPositionInfo/CSymbolInfo for state.
Sources: https://docs.mql4.com/trading/ordersend , https://www.mql5.com/en/articles/13229

### A2. "Simple" EA vs long tail

Canonical simple EA (the tutorial archetype, thousands of near-clones in CodeBase): OnTick → detect new bar → read fast MA and slow MA at shift 1 and 2 → if fastMA[1] > slowMA[1] && fastMA[2] <= slowMA[2] and no open position with this magic → OrderSend(OP_BUY, fixedLots, Ask, slip, Ask - SL_pips*Point, Ask + TP_pips*Point). Mirror for sell. This is exactly your DSL: crossover = comparison AND negated comparison at offset+1; exits are static SL/TP; sizing is fixed lots. Example thread: https://www.mql5.com/en/forum/296230/page3

The long tail (what the retail forex EA ecosystem actually sells/runs) is dominated by code-level order-management logic that is NOT a condition tree:
- Grid: open additional positions every N pips against (or with) price, shared basket TP; position count and average-price computation are loop-and-state over the order pool.
- Martingale / "recovery": lot = lastLot * multiplier after a loss; requires trade-history-dependent state.
- Hedging (MT4/MT5-hedging mode): simultaneous long+short baskets, lock/unlock logic.
- Coded trailing: per-tick OrderModify driven by profit-in-pips thresholds, breakeven moves, partial closes (OrderClose with fraction of lots).
- Equity-level logic: close-all at basket profit %, drawdown cutoffs, time filters, news filters (external calendar calls).
Evidence of prevalence: grid/martingale EAs are so common that prop-firm rulebooks ban them as a category, and the best-selling MQL5 Market gold EAs are explicitly grid-recovery hybrids (EA Gold Stuff 500+ reviews; "Waka Waka" grid; whole "Gridingale" genre). Sources: https://fortraders.com/blog/best-mt5-expert-advisors-eas-for-funded-accounts , https://newyorkcityservers.com/blog/best-forex-grid-eas-robots-2026 , https://www.mql5.com/en/market/product/42439

### A3. Determinism issues (important for verification diffing)

- Tick-dependence: OnTick fires per quote; two brokers deliver different tick streams (no centralized FX tape), so a per-tick EA produces different trades per broker even with identical code. EAs that gate on new-bar and use shift>=1 indicator values are the deterministic subset — this is exactly the subset your DSL models.
- Strategy Tester tick generation (MT5, same concepts in MT4): three modes —
  (1) "Every tick": ticks synthesized from M1 OHLC via a documented interpolation pattern (not real ticks); MT5 adds "Every tick based on real ticks" where broker tick history exists.
  (2) "1 minute OHLC": OnTick called only at the 4 OHLC control points of each M1 bar — known systematic bias: within a bar the tester assumes an O→H→L→C or O→L→H→C path, so intrabar SL/TP race resolution is guessed.
  (3) "Open prices only": OnTick called once per bar at open; only safe for EAs that trade strictly on bar-open with no intrabar SL/TP logic — the docs explicitly warn results in rough modes can be falsely good.
  Sources: https://www.mql5.com/en/docs/runtime/testing , https://www.metatrader5.com/en/terminal/help/algotrading/test_preparation , https://www.mql5.com/en/articles/2612
- MT4 "modeling quality %" measures interpolation coverage, not data correctness; community standard for serious MT4 backtests is importing Dukascopy tick data via Tickstory/TDS to reach "99.9%" with variable spread. Spread handling is itself a determinism hole: MT4's default tester uses the CURRENT fixed spread unless tick data with recorded spread is injected. Sources: https://www.earnforex.com/guides/quality-metatrader-historical-data/ , https://www.forexfactory.com/thread/768940-how-to-get-999-modeling-quality-on-mt4 , https://www.backtestmarket.com/en/blog/mt4-backtesting-data-sources
- Consequence for your translator: a translated bar-close DSL run should be diffed against an MT5 test in "Open prices only" (if the EA is new-bar-gated) or "1-minute OHLC"; expecting trade-for-trade equality against "every tick" is unrealistic for anything with intrabar SL/TP (your engine must model the same intrabar OHLC path assumption to match SL/TP fill ordering).

### A4. Strategy Tester report format

- MT4: "Report" tab → right-click → Save as Report → single .htm file: summary block (Bars/Ticks modelled, Modelling quality %, Initial deposit, Total net profit, Gross profit/loss, Profit factor, Expected payoff, Absolute/Maximal/Relative drawdown, trade counts, win %, consecutive wins/losses) + a full trade table with columns: # | Time | Type (buy/sell/s/l/t/p/modify/close/close at stop) | Order ticket | Lots | Price | S/L | T/P | Profit | Balance. Sources: https://www.metatrader4.com/en/trading-platform/help/autotrading/tester/tester_results , https://www.tradingpedia.com/metatrader-4-for-beginners/metatrader-4-strategy-tester-results-tab/
- MT5: Backtest tab (stats: net profit, profit factor, expected payoff, drawdowns, recovery factor, Sharpe, margin level, trade breakdown) plus separate Orders and Deals lists; right-click exports as HTML page or XML (Excel-compatible) table; exported columns match the enabled context-menu columns. Community parsers exist (e.g. "TesterReport" CodeBase library that reads a saved report back into deals/trades: https://www.mql5.com/en/code/78720 ). Sources: https://www.earnforex.com/guides/how-to-backtest-in-metatrader-5-strategy-tester/ , https://www.metaquotes.net/en/metatrader5/news/5430
- Practical verification key: both platforms give per-trade open/close time+price+SL/TP — enough for trade-level diffing; MT4's .htm is a stable, trivially scrapeable table format that the EA-vendor world has treated as the lingua franca for ~20 years.

### A5. Corpus size

- MQL5 Market: MetaQuotes markets "the largest store of trading applications"; MQL5's own article copy claims ~27,000 ready-made applications; the paid MT5 market listing alone paginates ~298 pages (~36/page ≈ 10k+ products in one category), plus MT4 market, plus Free sections. Sources: https://www.mql5.com/en/market , https://www.metaquotes.net/en/services
- MQL5.community: MetaQuotes claims >7,000,000 monthly visitors and bills it as the largest algo-trading community; CodeBase hosts a free source library with thousands of EAs/indicators dating to 2004 (MQL4) — that free corpus is the most translator-relevant because source is public. Sources: https://www.metatrader5.com/en/news/2275 , https://www.mql5.com/
- Beyond the marketplace: ForexFactory/EarnForex/github host enormous grey corpora of .mq4 source; MT4's longevity means the installed base of simple MA/RSI/SL-TP EAs is very large even as MetaQuotes pushes MT5.

### A6. Translatability estimate (reasoned, not sourced)

- By construct audit: an EA is translatable to your DSL iff (a) entry = boolean expr over indicator/price values at shift>=1 (or new-bar-gated shift 0), (b) exits = static-at-entry SL/TP, fixed trailing rule, or opposite-signal close, (c) sizing = fixed lots or simple equity %, (d) max one position per direction (magic-gated), no grid/averaging, no basket logic, no OrderModify beyond trailing, no time/news filters you don't support.
- Free CodeBase / tutorial-descended corpus: roughly 40–60% fits or nearly fits (MA cross, RSI OB/OS, MACD, Bollinger-touch with SL/TP are the dominant free archetypes; the rest are trailing-stop utilities, grid demos, and tick scalpers).
- Commercial MQL5 Market corpus: much lower — plausibly 10–20% — because the paid meta favors grid/martingale/recovery/"AI" EAs precisely because their equity curves look smooth; also sources are closed (.ex4/.ex5), so marketplace EAs are mostly non-translatable for the separate reason that you only have binaries.
- Best wedge: "simple + SL/TP + trailing-by-fixed-distance" covers the overwhelming majority of what beginners actually write and post to forums for help — that is the realistic intake funnel, not the Market.

## B) EasyLanguage (TradeStation)

### B1. Syntax shape and strategy structure

Pascal-ish, case-insensitive, series-oriented. Canonical strategy skeleton:
```
Inputs: FastLen(9), SlowLen(18), StopAmt(500);
Variables: FastAvg(0), SlowAvg(0);
FastAvg = Average(Close, FastLen);
SlowAvg = Average(Close, SlowLen);
If FastAvg crosses over SlowAvg then Buy ("LE") next bar at market;
If FastAvg crosses under SlowAvg then SellShort ("SE") next bar at market;
SetStopLoss(StopAmt);
```
Key constructs:
- Inputs(default) = optimizer-exposed parameters; Variables(init) persist across bars (each var is implicitly a series; myVar[2] = its value 2 bars ago). Historical reference uses square brackets: Close[1], Average(Close,10)[3] — direct analog of your bar offsets.
- Four order verbs with fixed position semantics: Buy (open/add long), SellShort (open/add short), Sell (close long only), BuyToCover (close short only). Every order statement must say when ("next bar" or "this bar on close" — the latter is a backtest-only fiction) and how (at market / at X stop / at X limit).
- Built-in exit/convenience functions: SetStopLoss(dollars), SetProfitTarget(dollars), SetPercentTrailing(profit, pct), SetDollarTrailing, SetBreakEven, SetExitOnClose; these are bar-by-bar managed exits evaluated intrabar by the engine, not user code — they map almost 1:1 onto your exit block (dollar→price-distance conversion needed via BigPointValue).
- Built-in state words: MarketPosition (-1/0/1), BarsSinceEntry, EntryPrice, CurrentContracts, AvgEntryPrice — commonly used in conditions ("If MarketPosition = 0 and ...").
- Signals are composed in the platform: a chart "strategy" = one or more inserted signals + global settings (commission, slippage, max contracts, pyramiding on/off).
Sources: https://cdn.tradestation.com/uploads/EasyLanguage-Essentials.pdf , https://cdn.tradestation.com/uploads/Learning-EasyLanguage-Strategies.pdf , https://georgepruitt.com/wp-content/uploads/2025/01/EZLang-CheatSheet.pdf , https://en.wikipedia.org/wiki/EasyLanguage

### B2. Declarative vs stateful in practice

- The default execution model is strongly aligned with your DSL: with IntrabarOrderGeneration = FALSE (the default), the whole script evaluates once per bar at bar close (BarStatus(1)=2), and "next bar" orders fill at the next bar's open at the earliest — i.e., deterministic bar-close evaluation with next-bar-open fills is EasyLanguage's native semantics. Sources: https://markplex.com/free-tutorials/tutorial-30-easylanguage-strategies-intrabarordergeneration-set-false-true/ , https://www.multicharts.com/trading-software/index.php?title=IntraBarOrderGeneration
- Statefulness in typical scripts: Variables persist across bars, so the long tail freely writes imperative accumulators (highest-high-since-entry tracked manually, setup/trigger two-stage flags, counters, "once" latches). But a large share of published strategies use variables only as named subexpressions (var = Average(...); if var > ... ) which flattens into a pure expression tree. MarketPosition/BarsSinceEntry/EntryPrice references are the most common genuinely stateful constructs — your DSL can absorb the first as implicit (one-position model), BarsSinceEntry as a time-stop exit primitive, EntryPrice inside the exit block only.
- IntrabarOrderGeneration = TRUE flips evaluation to every tick ("next bar" becomes "next tick") — such strategies leave your determinism envelope. Source: https://nexusfi.com/showthread.php?t=58107

### B3. Corpus / community status (2026)

- Legacy-leaning but alive: the language dates to 1991 (TradeStation/Omega Research), with a knowledge base "continually added to since the late 1980s" per MultiCharts marketing; PowerLanguage (MultiCharts) is an EasyLanguage-compatible dialect specifically so the legacy corpus ports. Sources: https://www.multicharts.com/features/easylanguage/ , https://en.wikipedia.org/wiki/MultiCharts
- TradeStation the broker reports on the order of 150k+ active accounts; its own forums are widely described as quiet, and community energy has migrated to MultiCharts forums, nexusfi (futures.io), and independent educators (George Pruitt, Markplex) who still publish actively. Net: a large static corpus of 30 years of strategies (books: Pruitt's "Building Winning Trading Systems", TS&C magazine's monthly "Traders' Tips" publish EasyLanguage for every featured system), small inflow of new authors. It is a legacy-rich, growth-poor ecosystem — ideal as a translation SOURCE (big frozen corpus, stable semantics), poor as a destination. Sources: https://www.elitetrader.com/et/threads/question-tradestation-easylanguage.347073/ , https://georgepruitt.com/tag/easylanguage-code/ , https://money.usnews.com/investing/best-brokers/tradestation
- Side note: TS&C "Traders' Tips" corpus is a uniquely clean benchmark set — each system exists in parallel official EasyLanguage / thinkScript / AFL / NinjaScript implementations, perfect for cross-language translator testing.

### B4. Translatability

High — the highest of the three. Default IOG=FALSE semantics equal your evaluation model; the Set* exit family is literally your exit block; crosses over/under, >, <, and bracketed offsets are your leaves; Inputs are your params block. Blockers: hand-rolled stateful vars (latches/counters), pyramiding (Buy adds to position when enabled), intrabar strategies, multi-data (Data2) references, and dollar-denominated stops (need point-value metadata). Estimate: 60–75% of published "book/magazine/forum" EasyLanguage strategies translate cleanly or with mechanical rewriting of named vars; the stateful residue is mostly time-stops and trailing logic you can map to dedicated exit primitives.

## C) thinkScript (Schwab thinkorswim)

### C1. What it expresses

Three artifact types from one language: studies (chart plots: plot x = ...), scans/watchlist columns (a single boolean/number per symbol), and strategies (studies that call AddOrder to paint simulated entries/exits). Alerts can be attached to study values. Critical limit, from the official tutorial: "All the signals you get are hypothetical, i.e., you cannot send real orders using strategies" — thinkScript strategies are backtest/visualization only; there is no automated execution pathway in thinkorswim at all. Sources: https://toslc.thinkorswim.com/center/reference/thinkScript/tutorials/Basic/Chapter-7---Creating-Strategies , https://toslc.thinkorswim.com/center/reference/thinkScript

AddOrder mechanics (full signature): AddOrder(int type, IDataHolder condition, IDataHolder price, IDataHolder tradeSize, CustomColor tickColor, CustomColor arrowColor, String name). Order types: OrderType.BUY_AUTO / SELL_AUTO (auto = flip/open-or-close) and BUY_TO_OPEN / BUY_TO_CLOSE / SELL_TO_OPEN / SELL_TO_CLOSE. The order "is added for the next bar when the condition is true"; default fill price is open[-1] — i.e., NEXT bar's open, expressed via thinkScript's negative-offset future reference. tradeSize overrides global strategy settings. Right-clicking a signal → "Show report" yields the strategy report (list of hypothetical trades + P/L; FloatingPL study plots running P&L). Sources: https://toslc.thinkorswim.com/center/reference/thinkScript/Functions/Others/AddOrder , Chapter 7 link above.

No stop/TP/trailing primitives exist: exits must themselves be AddOrder(...TO_CLOSE, condition) rules, so people encode stops as conditions like close < entryPrice - stopAmt using EntryPrice() — intrabar stop fills cannot be modeled (bar-granularity only). This actually matches a bar-close DSL better than it matches a real broker.

### C2. How declarative is it — verified

Genuinely (near-)declarative. A script is a set of def/plot bindings over whole series; there is no mutation, no statements-executed-in-order side effects, no loops (the only iteration construct is the fold expression, a bounded functional fold: fold i = 0 to n with acc do ...), no arrays (every variable IS a time-series), and user-defined "functions" are expression-scoped script {} blocks. Bar offsets are bracket syntax: close[1] (past), open[-1] (future, used for next-bar fills). Comparisons and and/or/not over defs ARE a condition tree already. Sources: https://toslc.thinkorswim.com/center/reference/thinkScript/Reserved-Words/fold , https://jshingler.github.io/TOS-and-Thinkscript-Snippet-Collection/TOS%20&%20Thinkscript%20Collection.html , https://www.hahn-tech.com/ans/limits-on-script-command/

### C3. rec — the stateful escape hatch

rec declares a variable whose definition references its own prior value: rec c = c[1] + volume. Official docs note rec is legacy — def now supports self-reference identically, so stateful code today usually looks like def x = if cond then close else x[1]; with CompoundValue(1, expr, init) used to seed the recursion. How common: very common in the community corpus for exactly the things your DSL externalizes — trailing stops, "price at last signal" memory, latch/flag logic, cumulative counters. Benign uses (ubiquitous): every EMA/Wilder-smoothed indicator is internally recursive, but those collapse to named indicators in your DSL. Heuristic for the translator: recursion inside a known indicator definition → map to indicator leaf; recursion at strategy-logic level → stateful, reject or map to trailing/exit primitives. Sources: https://toslc.thinkorswim.com/center/reference/thinkScript/Reserved-Words/rec , https://www.hahn-tech.com/ans/how-to-make-a-variable-retain-its-value-on-successive-bars/

### C4. Community / corpus

Scripts are shared as plain text or thinkorswim shared-item links (tos.mx). Hubs: useThinkScript.com — self-described largest thinkScript repository, ~21,000+ registered members, 87,000+ posts, Indicators forum alone ~2.3K threads / 42K messages; also Hahn-Tech Q&A, r/thinkorswim, scattered GitHub gists, and the official Learning Center reference. thinkorswim itself sits on Schwab's multi-million-active-trader base, so the addressable user pool is the largest of the three platforms even though the scripting community is mid-sized. Sources: https://usethinkscript.com/ , https://usethinkscript.com/threads/the-universe-of-thinkscript-your-one-stop-research-shop.300/ , https://www.schwab.com/learn/story/coding-traders-building-your-own-indicator

### C5. Translatability

Highest ceiling, modest corpus of true "strategies": the language is already a dataflow condition tree with explicit bar offsets and next-bar-open fills — AddOrder(type, condition, open[-1]) is almost literally your JSON. Most shared scripts are STUDIES (plots/alerts), not AddOrder strategies, but a study's signal condition converts directly to an entry condition. Blockers: strategy-level rec/def-recursion (latches, trailing memory), fold expressions, GetValue() dynamic indexing, secondary-aggregation references (close(period = AggregationPeriod.DAY)) if you don't do multi-timeframe, and EntryPrice()-based exits (map to exit block). Estimate: 70%+ of AddOrder strategies and the majority of alert/scan conditions translate; study-only visual scripts (colored candles, labels) are out of scope rather than untranslatable.

## D) Brief: NinjaScript and AmiBroker AFL

NinjaScript (NinjaTrader 8, C#): full C# class inheriting Strategy; lifecycle via OnStateChange() (State.SetDefaults configures name, Calculate = Calculate.OnBarClose | OnEachTick | OnPriceChange, order-fill resolution; State.DataLoaded instantiates indicator objects like SMA(Close, 14)); per-bar logic in OnBarUpdate() with indexed series (Close[0] current, Close[1] prior); managed order API EnterLong()/EnterShort()/ExitLong() plus declarative-ish SetStopLoss(CalculationMode.Ticks|Price|Percent|Currency)/SetProfitTarget()/SetTrailStop(); helpers CrossAbove(a,b,lookback)/CrossBelow. Translatability: the Calculate.OnBarClose + managed-approach + Set* subset is cleanly translatable (entry condition tree + your exit block, with CalculationMode mapping); but being arbitrary C#, the long tail uses unmanaged orders, OnOrderUpdate/OnExecutionUpdate event state machines, class fields as persistent state, and multi-series AddDataSeries — static translation only works by pattern-matching the strategy-wizard/tutorial template, which fortunately is how a large share of shared scripts are written (the built-in Strategy Builder generates exactly this shape). Sources: https://www.horizontrading.ai/learn/ninjascript-tutorial-code-your-first-ninjatrader-strategy , https://newsletter.huntgathertrade.com/p/strategy-template-for-ninjatrader , https://nocnoe.com/blog/building-custom-ninjatrader-strategies-ninjascript

AmiBroker AFL: array/vector language — every expression evaluates over the whole price history at once; a strategy is just assignments to reserved signal arrays Buy / Sell / Short / Cover (1 = signal on that bar), optional BuyPrice/SellPrice arrays, position sizing via SetPositionSize(), and stops via the built-in ApplyStop(type = stopTypeLoss|stopTypeProfit|stopTypeTrailing|stopTypeNBar, mode = stopModePercent|stopModePoint, amount) which the backtester executes internally. Example: Buy = Cross(MA(C,10), MA(C,50)); Sell = Cross(MA(C,50), MA(C,10)); ApplyStop(stopTypeLoss, stopModePercent, 2);. This is the most structurally congruent language to your DSL of all five — Buy/Sell ARE condition trees, Ref(x,-1) is your bar offset, ApplyStop is your exit block, stopTypeNBar is a time stop. Blockers: AFL also permits imperative loops (for/while), the custom backtester interface (SetCustomBacktestProc) for portfolio logic, and #include'd stateful code — but idiomatic single-symbol AFL avoids all of it, so the translatable fraction of typical published AFL (e.g. Traders' Tips, wisestocktrader.com corpus) is very high, plausibly 70%+. Sources: http://amibroker.com/guide/afl/equity.html , https://forum.amibroker.com/t/how-to-include-short-and-cover-into-my-trading-formula/18980 , https://www.mail-archive.com/amibroker@yahoogroups.com/msg02383.html

## Cross-cutting conclusions for translator design

1. Semantic common denominator across all five: "condition true at bar close N → fill at open of bar N+1". EasyLanguage (IOG=false), thinkScript (open[-1] default), AFL (default trade delays), NinjaScript (Calculate.OnBarClose) all natively use it; MQL has no native bar event but the deterministic subset of EAs emulates exactly it (new-bar gate + shift-1 indicators). Make next-bar-open fills your DSL's canonical fill rule and verification diffs become feasible.
2. The universal untranslatable residue is the same three things everywhere: (a) arbitrary persistent state (latches/counters/grid baskets), (b) intrabar/tick-mode evaluation, (c) order-management loops (averaging, pyramiding, partial closes). Detect these as explicit reject reasons rather than failing opaquely.
3. Ordering by translator ROI: MQL4/5 has by far the largest corpus and user base but the lowest clean-translation rate (grid/martingale-heavy commercial tail; best intake is forum/CodeBase simple EAs, est. 40–60% of that subset). EasyLanguage has a large frozen corpus with the friendliest default semantics (est. 60–75%). thinkScript is the most language-level congruent and its users have NO execution path today (strategies are simulation-only), making them the most motivated migrators (est. 70%+ of AddOrder strategies). AFL is nearly isomorphic to the DSL; NinjaScript is translatable only in its wizard/template subset.
4. For verification: MT4 .htm / MT5 HTML-XML tester reports give per-trade tables suitable for automated diffing; thinkorswim's strategy report is chart-bound (right-click → show report, manual export) — expect to re-simulate rather than diff; TradeStation performance reports export to Excel. The TS&C "Traders' Tips" archive provides the same strategies implemented officially in EasyLanguage, thinkScript, AFL, and NinjaScript — use it as a cross-language golden test set.

---

# Report 4 — Declarative / no-code formats

(for building import adapters into a JSON condition-tree DSL; researched 2026-11-04)

## A) COMPOSER.TRADE "SYMPHONIES" — the priority target

### A1. The serialized format (fully reverse-engineered + now officially documented)

A symphony is a **tree of nodes**, natively serialized as **EDN** (Clojure Extensible Data Notation) — field names are EDN keywords (`:step`, `:children`). Composer's official API and MCP server expose the **same tree as JSON** (keyword names minus the leading colon, keeping kebab-case and trailing `?`). Every node has `:id` (UUID), `:step` (node type), and usually `:children`.

**Node types (`:step` values):**
- `:root` — metadata: `:name`, `:description`, `:rebalance` (`none|daily|weekly|monthly|quarterly|yearly`), `:rebalance-corridor-width` (threshold rebalancing; only valid when rebalance is `none`). Exactly one child, which must be a weight node.
- `:wt-cash-equal` — equal weight across children.
- `:wt-cash-specified` — children carry `:weight {:num N :den 100}` fractions; must sum to 100.
- `:wt-inverse-vol` — inverse volatility weighting, `:window-days` (computed from stdev of returns).
- `:wt-marketcap` — market-cap weighting (in legacy parsers; not in the current MCP schema).
- `:if` — children are exactly a tuple (if-child true-branch, if-child else-branch).
- `:if-child` — the branch. Else branch: `:is-else-condition? true`. The condition branch carries the comparison inline: `:lhs-fn`, `:lhs-val` (ticker), `:lhs-window-days`, `:comparator` (`:gt :gte :lt :lte :eq`), `:rhs-fn`, `:rhs-val`, `:rhs-window-days`, `:rhs-fixed-value?` (true ⇒ `:rhs-val` is a number literal, not a ticker-indicator). Newer serializations also allow `:lhs-fn-params` / `:rhs-fn-params` `{window: int}`.
- `:filter` — top-N selection: `:select-fn` (`:top`/`:bottom`), `:select-n` (string int), `:sort-by-fn` (indicator), `:sort-by-window-days`; children are candidate assets; selected assets get equal 1/N of the filter's weight.
- `:group` — cosmetic named sub-strategy (`:name`, `:collapsed?`); exactly one weight-node child.
- `:asset` — leaf: `:ticker` plus ephemeral derived fields `:name`, `:exchange`, `:price`, `:dollar_volume`, `:has_marketcap`. Crypto tickers use `CRYPTO::BTC//USD` format; "cash" is represented by BIL.
- `:empty` — empty block (MCP schema only).

**Real serialized example (condition node, from a captured backtest payload):**
```edn
{:symphony {:id "U917ZWjlPahB5eyIrvxh", :step :root, :name "Copy of Simple S&P 500",
 :rebalance :daily, :children [
  {:step :wt-cash-equal, :children [
   {:weight {:num 100, :den 100}, :step :if, :children [
    {:step :if-child, :is-else-condition? false,
     :lhs-fn :moving-average-price, :lhs-window-days "21", :lhs-val "SPY",
     :comparator :gt,
     :rhs-fn :moving-average-price, :rhs-window-days "210", :rhs-val "SPY",
     :children [{:step :asset, :ticker "QQQ", :exchange "XNAS", ...}]}
    {:step :if-child, :is-else-condition? true, :children [...]}]}]}]}}
```
Fixed-value RHS variant: `:rhs-fixed-value? true, :lhs-fn :relative-strength-index, :lhs-window-days "10", :comparator :lt, :rhs-val "30"`.

**Real filter node example:**
```edn
{:step :filter, :select? true, :select-fn :bottom, :select-n "1",
 :sort-by? true, :sort-by-fn :relative-strength-index, :sort-by-window-days "13",
 :weight {:num "80", :den 100},
 :children [{:step :asset, :ticker "UVXY", ...} {:step :asset, :ticker "VIXY", ...}]}
```

The backtest payload wrapper (what the web client POSTs) adds: `:capital`, `:start-date-in-epoch-days`, `:end-date-in-epoch-days`, `:slippage-percent`, `:apply-taf-fee?`, `:apply-reg-fee?`, `:ticker-benchmarks`.

**Authoritative modern schema**: Composer's own MCP package ships a Pydantic schema (`symphony_score_schema.py`) mirrored at https://github.com/tanwithme/composer-trade-mcp (fork of the now-removed invest-composer/composer-trade-mcp; PyPI: `composer-trade-mcp`). Key invariants: Root/Group must have exactly one weight-node child; `If.children` is exactly (IfChildTrue, IfChildFalse); `WeightMap = {num: float>0, den: 100}`; comparators `gt|gte|eq|lt|lte`; supported crypto list of 22 symbols.

Best parser references:
- https://github.com/jamesfulford/symphony-orchestrator (`lib/logic.py` documents every node field + weight-propagation reducer; `lib/traversers.py` shows indicator extraction) — androslee/compose_symphony_parser is a fork with example inputs (`inputs/*.edn`, incl. bad inputs) and transpilers to human/QuantConnect/vectorbt: https://github.com/androslee/compose_symphony_parser
- Online converter symphony-URL → clean JSON + IF/ELSE tree: https://composeratlas.com/converter

### A2. Indicator/metric functions (exact list)
From the official MCP schema enum (`Function`) — kebab-case, identical in EDN with leading colon:
`current-price`, `cumulative-return`, `moving-average-price`, `moving-average-return`, `exponential-moving-average-price`, `relative-strength-index`, `standard-deviation-price`, `standard-deviation-return`, `max-drawdown`.
Commented out "not supported yet" in the schema (i.e., roadmap): `percentage-price-oscillator(+signal)`, `moving-average-convergence-divergence(+signal)`, `lower-bollinger`, `upper-bollinger`. All take a single `window-days` parameter; conditions compare indicator(tickerA, windowA) vs indicator(tickerB, windowB) or vs fixed numeric value. That's the whole condition vocabulary — an adapter needs exactly 9 functions, 5 comparators, ticker-or-literal RHS.

### A3. Rebalance semantics
- Logic is evaluated once per trading day on **daily bars**, with live execution in a trading window **near market close** (final market hour); backtests evaluate on daily closes. Sources: https://alphagaindaily.com/en/blog/composer-ai-trading-review, https://www.allinallspace.com/trading-tools-reviews/composer-ai-review/
- `rebalance: daily|weekly|monthly|quarterly|yearly` = calendar rebalancing; conditional branches re-evaluate on the schedule.
- **Threshold trading**: `rebalance: none` + `rebalance-corridor-width` — trade only when current holdings drift beyond the corridor from target weights; with conditionals, a branch switch only trades if the threshold is also breached. https://help.composer.trade/article/76-threshold-trading

### A4. Export / API / community scale
- **Official REST API** (https://api.composer.trade/docs/index.html): `GET /api/v0.1/symphonies/{id}/score` returns the EDN definition; `POST /symphonies` creates from a logic tree; `PATCH .../versions/{vid}/score/nodes` patches individual nodes; `POST /backtest` backtests a **custom symphony definition** without saving; plus deploy/invest/liquidate/rebalance-now, dry-run trade preview, `POST /search/symphonies` over the public library. Auth: `x-api-key-id` + Bearer secret (Settings → API Access). Rate limits 25–250 req/min.
- Any public symphony has a share URL (`composer.trade/symphony/{id}/details`); the serialized tree is retrievable from backtest network traffic even without the API (the technique the GitHub parsers used).
- Community scale: **~175,000 investors**, **2,000–3,000+ community-built symphonies** in the public library.

### A5. Business state 2024–2026
- Alive and growing; raised Series A ~2022 (FINRA-registered broker-dealer; executes via its own brokerage).
- **Aug 2025**: launched **options trading** + the **official Composer MCP server** (remote URL `https://ai.composer.trade/mcp`, 25+ tools incl. `create_symphony`, `backtest_symphony`, `invest_in_symphony`, `execute_single_trade`) — "vibe trading." https://x.com/ComposerTrade/status/1958195429058752864
- **Oct 21, 2025**: "Trade with AI" feature launch. https://www.tradersmagazine.com/xtra/composer-introduces-trade-with-ai-to-enhance-investment-platform/
- Crypto: had direct crypto symphonies (22 assets, `CRYPTO::X//USD`), **ended direct crypto/crypto-indicator support after Jan 31, 2026**.
- **Jun 23, 2026: acquired by SoFi**, now "Composer by SoFi"; symphonies/pricing/custody unchanged at announcement. Pricing: Trading Pass $40/mo or $384/yr. https://thepaypers.com/mergers-aquisitions-and-investments/news/sofi-acquires-ai-startup-composer-to-democratise-trading-strategies, https://www.therundown.ai/tools/composer

Adapter verdict: highest-value target. Closed vocabulary, clean recursive tree, officially retrievable serialized form, and an official Pydantic schema to validate against.

## B) OTHER DECLARATIVE / NO-CODE BUILDERS

### B1. TrendSpider
No-code Strategy Tester: visual builder of entry/exit rule trees (indicator comparisons, candle patterns, AND/OR groups, multi-timeframe), deployable as alerts or "Strategy Bots." Strategies are saved server-side and shared via **links / TrendSpider Store templates** — **no public JSON export or documented serialization**; adapter would have to target their natural-language importer or screen-level recreation. https://trendspider.com/product/strategy-development-and-backtesting-tools/, https://help.trendspider.com/kb/strategy-tester. User base: ~tens of thousands (not disclosed; no 2025 figure found).

### B2. Crypto IF-THEN builders
- **Coinrule** (alive): IF-THEN rule engine (price thresholds, indicator triggers, coin-performance comparisons, time schedules; and/or sequences, waiting periods; buy/sell/notify actions). Has a **B2B REST API v3** (`https://api.coinrule.com/v3`, OpenAPI spec) for programmatic rule creation, and inbound **custom-signal webhooks** (unique URL per rule). Rule JSON schema is partner-gated (the public GitBook schema link is broken). https://coinrulehq.gitbook.io/docs/beta-api-v3, https://help.coinrule.com/articles/151602-using-custom-signals-on-coinrule. Claims ~250k users historically.
- **Mudrex**: original drag-and-drop Strategy Builder / Mudrex Invest **retired**; pivoted to Indian exchange + "Coin Sets" (thematic auto-rebalanced baskets). Not an adapter target. https://coincodecap.com/mudrex-review
- **Tuned.com**: went dark, acquired by SageMaster May 2023, reopened to new signups **Feb 2025**. Strategies are script-based (their own scripting on top of exchanges), not a declarative export format. Niche user base. https://www.globenewswire.com/news-release/2023/05/09/2664802/0/en/
- **Kavout**: pivoted to AI research/screening (InvestGPT, K-Score) — no strategy format at all.
- **StockHero** (alive, stocks + crypto): no-code bot builder (entry/exit indicator conditions, DCA/Grid/Wheel/Iron Condor presets) + a **bot marketplace for renting bots** (stockheromarket.com). Bots shared/cloned only inside the platform; no export. https://daytradingtoolkit.com/reviews/stockhero-review

### B3. Option Alpha (options autotrading, no-code)
Bots = **Scanner automations** (filter market → open position) + **Monitor automations** (Position Loop → manage/exit) + **Triggers** (date, recurring schedule, market open/close, position opened/closed). Logic is built from "decision recipes" in natural-language-parameterized blocks with Yes/No branches — i.e., a decision tree. Sharing: one-click **bot templates and shareable single automations** (private/public, community library) — but via platform clone-links, **no documented JSON export**. https://docs.optionalpha.com/tools/bots/automations, https://optionalpha.com/blog/share-bot-automations-just-as-easily-as-bot-templates, https://optionalpha.com/help/templates-and-cloning. Decision vocabulary is rich (IV rank, delta, DTE, P/L%, probability ITM) — would map to your DSL only if they ever expose the serialization.

### B4. TradersPost / webhook signal routing — the de facto interchange JSON
TradersPost's webhook schema is the closest thing to a **de facto standard for signal-level interchange** (TradingView → broker). Full reference: https://docs.traderspost.io/docs/developer-resources/webhook-reference
- Endpoint: `POST https://webhooks.traderspost.io/trading/webhook/{uuid}/{password}`
- Required: `ticker`, `action` ∈ `buy|sell|add|resize|exit|reverse|breakeven|cancel`
- Core optional: `sentiment` (`bullish|bearish|flat|long|short`), `quantity` + `quantityType` (`fixed_quantity|dollar_amount|risk_dollar_amount|risk_percent|percent_of_equity|percent_of_position`), `orderType` (`market|limit|stop|stop_limit|trailing_stop`), `price`, `limitPrice`, `stopPrice`, `trailAmount|trailPercent`, `timeInForce` (`day|gtc|gtd|opg|cls|ioc|fok`)
- Risk blocks: `takeProfit {limitPrice|percent|amount|pnlAmount}`, `stopLoss {type, percent|amount|stopPrice|limitPrice|trailAmount|trailPercent|pnlAmount}`
- Options: `optionType`, `expiration` (absolute or `+6 months`), `expirationTime` (`zero-dte|weekly|monthly|...`), `strikePrice|strikesAway`
- Ops: `cancel`, `cancelAfter`, `delay`, `rejectAfter`, `expiresAt`, `test`, `extras`; batch = root-level array of ≤5, all-or-nothing.
Example:
```json
{"ticker":"AAPL","action":"buy","quantity":100,"quantityType":"fixed_quantity",
 "orderType":"market","sentiment":"bullish","timeInForce":"day",
 "takeProfit":{"percent":5},"stopLoss":{"type":"stop","percent":2},
 "time":"2024-01-15T14:30:00Z"}
```
The minimal TradingView-alert convention everyone copies: `{"ticker":"{{ticker}}","action":"{{strategy.order.action}}","sentiment":"{{strategy.market_position}}","price":"{{close}}"}`. https://docs.traderspost.io/docs/learn/signal-sources/tradingview. Note: this is signal interchange (imperative orders), not strategy interchange — useful as an *output* adapter from your DSL, not an input.

### B5. Open-standard attempts for strategy interchange
There is **no adopted open standard**. What exists:
- **TRADE.md** (scaled-agents): a 2025-26 spec for describing a strategy (thesis + signals + risk + sizing + gates + lineage) in a markdown/structured file aimed at *coding agents and execution engines*, with CLI `trade-md lint/explain/compile` (compile target: freqtrade), spec v0.2, `pip install trade-md`. Caveat: the GitHub repo (github.com/scaled-agents/TRADE-md) now 404s and the PyPI package is unreachable — appears pulled or renamed; treat as a signal of direction, not a dependency.
- **QuantConnect LEAN** `config.json` / `Optimizer.Launcher/config.example.json`: declarative only about *which compiled algorithm to run* (algorithm-type-name, language, parameters, environments) — not a strategy-logic format. https://github.com/QuantConnect/Lean/blob/master/Optimizer.Launcher/config.example.json
- Adjacent-only: trading-journal-schema (JSON Schema for trade logs, github.com/Indikator-tech/trading-journal-schema); FIX/FDC3 cover orders/desktop interop, not strategy logic. Academic: "Formulating Financial Trading Strategies Using LLM: A DSL-Mediated Approach via In-Context Learning" (IEEE 2025, 95.3% NL→DSL match rate) and a Springer companion paper — evidence the field is converging on exactly this architecture (NL → declarative DSL → engine). https://ieeexplore.ieee.org/abstract/document/11108657
- Practical takeaway: Composer's symphony tree is the closest thing to a lingua franca for condition-tree allocation strategies; TradersPost JSON is the lingua franca for signals.

## C) THE AGENT / MCP ANGLE (2025–2026)
- **Composer MCP server** — the flagship: official, remote (`https://ai.composer.trade/mcp`), 25+ tools; `create_symphony` takes the full JSON symphony-score tree (schema above), `backtest_symphony` gives the iterate loop; marketed as "vibe trading." An adapter that speaks symphony-score JSON is automatically LLM/MCP-interoperable. https://playbooks.com/mcp/invest-composer/composer-trade-mcp, https://lobehub.com/mcp/invest-composer-composer-trade-mcp
- **MT5 MCP servers**: MT5-Automation-Labs/mt5-backtesting-lab (Rust, compiles MQL5 EAs, runs Strategy Tester under Wine, SQLite results; active Oct 2026); Boschi404/mt5-mcp-server (37 tools: write EA → compile → backtest → optimize → Monte Carlo → Kelly → live). https://github.com/MT5-Automation-Labs/mt5-backtesting-lab, https://github.com/Boschi404/mt5-mcp-server
- **tradingview-mcp** (atilaahmettaner): 30+ tools for data/indicators/screeners/backtests into Claude/Cursor. **jesse-mcp** (bkuri): Jesse crypto framework via MCP. **ai-trader** (HKUDS, 1.1k+ stars): Backtrader harness with integrated MCP server.
- Curated index: https://github.com/LLMQuant/awesome-trading-agents (LLM trading agents, MCP servers, agent skills). Directory: https://mcp.so/tags/backtesting (11 backtesting MCP servers).
- Pattern worth noting: all of these either (a) generate *code* (MQL5/Python) or (b) pass a *declarative JSON tree* (Composer). Only Composer does (b) — a validated declarative schema is demonstrably the more LLM-reliable interface (bounded vocabulary, Pydantic-validatable), which is the same argument for a condition-tree DSL being the MCP surface.

### Key source URLs (deduped)
- https://github.com/jamesfulford/symphony-orchestrator · https://github.com/androslee/compose_symphony_parser · https://github.com/tanwithme/composer-trade-mcp (schemas/symphony_score_schema.py)
- https://api.composer.trade/docs/index.html · https://help.composer.trade/article/76-threshold-trading · https://composeratlas.com/converter
- https://x.com/ComposerTrade/status/1958195429058752864 · https://thepaypers.com/mergers-aquisitions-and-investments/news/sofi-acquires-ai-startup-composer-to-democratise-trading-strategies · https://www.therundown.ai/tools/composer
- https://docs.traderspost.io/docs/developer-resources/webhook-reference · https://docs.traderspost.io/docs/learn/signal-sources/tradingview
- https://coinrulehq.gitbook.io/docs/beta-api-v3 · https://help.coinrule.com/articles/151602-using-custom-signals-on-coinrule
- https://trendspider.com/product/strategy-development-and-backtesting-tools/ · https://docs.optionalpha.com/tools/bots/automations · https://optionalpha.com/help/templates-and-cloning
- https://daytradingtoolkit.com/reviews/stockhero · https://coincodecap.com/mudrex-review · https://www.globenewswire.com/news-release/2023/05/09/2664802/0/en/ (Tuned/SageMaster)
- https://github.com/QuantConnect/Lean/blob/master/Optimizer.Launcher/config.example.json · https://github.com/scaled-agents/TRADE-md (now 404) · https://ieeexplore.ieee.org/abstract/document/11108657
- https://github.com/LLMQuant/awesome-trading-agents · https://github.com/MT5-Automation-Labs/mt5-backtesting-lab · https://github.com/Boschi404/mt5-mcp-server · https://mcp.so/tags/backtesting
