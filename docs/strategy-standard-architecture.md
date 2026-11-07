# StratIR: Open Strategy Standard and Import/Export Architecture

Status: draft v0.3 · 2026-11-04
Companion document: [strategy-language-research-raw.md](./strategy-language-research-raw.md). All claims regarding external strategy languages are sourced there.

## 1. Overview

StratIR (Strategy Intermediate Representation) is the name for the declarative strategy format already implemented at the core of Paper Fleet (`core/expr.py`, `core/strategy.py`). The name reflects the format's role: an intermediate representation that multiple strategy languages lower into, and that can be lowered back out of to other targets.

Paper Fleet is the reference runtime and canonical home: the backtest engine, the verified track record, the leaderboard, and live execution. StratIR is the format those services operate on. The format is intended to be published as an open standard; the runtime and the accumulated proof remain the product.

The strategic thesis rests on three elements:

1. **Import pipeline.** Major strategy languages (Pine Script, Composer symphonies, thinkScript, EasyLanguage, AmiBroker AFL, MQL, and plain English) translate into StratIR through one universal frontend. Imports supply the installed base.
2. **Distribution via MCP and API.** StratIR is a format agents can emit. A validated declarative schema is a more reliable interface for language models than generated code (see research: Composer MCP, QuantPilot, and the IEEE 2025 NL-to-DSL paper reporting 95.3% match rate). Paper Fleet is positioned as the multi-market, feed-aware instance of this pattern.
3. **Published specification.** The schema is public, versioned, and permissively licensed. No adopted open standard for strategy interchange exists today; the one prior attempt (TRADE.md) is defunct. A working specification, a reference implementation, and a corpus together establish a standard. The import pipeline supplies the corpus.

StratIR functions as a hub rather than a one-way funnel: each language is a bidirectional spoke. Import is the acquisition path; the native runtime is the business; export (Section 7) is the credibility mechanism, since the ability to leave is what makes an open standard credible and is a precondition for trust.

## 2. Scope: existing system versus proposed work

Paper Fleet is a built, deployed, and monetized product. StratIR describes the outward extension of the format at its core. The two must not be conflated.

### 2.1 Already built and operational (Paper Fleet)

- **The format itself** — `core/expr.py` and `core/strategy.py`. The frontend types mirror it directly (`Compose.tsx` is annotated "types matching core/expr.py + core/strategy.py").
- **Three frontends already lowering into the format** — the visual builder (`routes/build/Compose.tsx`), the plain-English parser (`supabase/functions/parse-strategy`), and the context-aware assistant (`assistant/`), which drafts bots through the same parse path as the manual composer.
- **The deterministic engine** — `core/backtest.py` and `core/evaluator.py` (approximately 5,200 lines of core code), running backtest and live execution from a single evaluator.
- **The five-stage build flow** — Compose, Training, Trials, Weather, Deploy (`routes/build/stages.ts`). Trials performs statistical validation; Weather applies regime and timing gates.
- **The proof and social layer** — live fleet view, public leaderboard (ranked return, copy-to-draft forking), challenges, and feed.
- **Monetization** — Stripe integration (`create-checkout-session`, `create-portal-session`, `stripe-webhook`, and the upgrade page), with services running under systemd.

### 2.2 Proposed work (the subject of this document)

- **The import pipeline (Section 5)** — a fourth class of frontend that ingests foreign languages, not only English, the visual builder, and the assistant. This is the element that extends the format from application internals to interchange standard.
- **The export path (Section 7)** — lowering StratIR back out to Pine Script, MQL, and webhook formats.
- **The published specification (Section 11)** — formalizing the existing format as a versioned open standard with a reference validator.
- **Engine alignment for verification parity (Section 8)** — targeted changes (next-open fill mode, instrument metadata, warm-up handling) required because imported strategies must be diffed against foreign runtimes.

The musts, coulds, and shouldn'ts in Section 9 describe evolution of an existing, shipping format intended to widen import coverage. They do not describe a format being designed from scratch.

## 3. Design principles

These invariants govern all format evolution. Every entry in Section 9 is an application of them.

**P1 — Strategies are data, not code.** A strategy is a JSON document validated by `core.strategy.parse()`. No user code executes. This removes the need for sandboxing and resource limits, eliminates a class of exploits, and allows a strategy to be analyzed, diffed, rendered as UI, mutated programmatically, and emitted reliably by a language model against a schema.

**P2 — Determinism is the product.** Evaluation is a pure function of `(spec, candles, aux)` to signals. Identical spec and identical price data produce identical trades on every run. This property makes a track record re-derivable and therefore evidential, makes translation verifiable through replay and diff, and gives the agent optimization loop a stable objective. Any construct that breaks determinism is rejected categorically.

**P3 — Causality by construction.** No lookahead is expressible. Offsets read committed history; multi-timeframe and feed operands align to the most recent bar or event closed at or before the base bar's close (`core/expr.py`); feed staleness gates are engine-enforced. The backtest-inflation bugs common to imperative platforms cannot be written.

**P4 — The state rule.** State may enter the language only as a named, engine-owned primitive with declared bounds, never as a user-programmable mechanism. Trailing stops, breakeven, bars-since, and sample-and-hold qualify, because the engine owns the memory and the user declares intent. Variables, counters, flags, loops, and custom functions do not, because they convert the format into code and forfeit P1 through P3. This rule is the test for every proposed feature.

**P5 — Backtest equals live.** One evaluator and one spec serve both paths (`core/evaluator.py`, `core/backtest.py`). Divergence between simulation and execution is refused architecturally rather than reconciled operationally.

**P6 — Expressiveness grows centrally.** The response to "the format cannot express X" is the indicator registry and named primitives, added centrally, reviewed, deterministic, and versioned. It is never a user-level escape hatch (Section 9.3).

## 4. The format today (reference baseline)

The following is implemented in `core/` and already authored by the three live frontends described in Section 2.1. It constitutes version 0 of the published standard.

**Strategy envelope** (`core/strategy.py`): `name`; `side` (long, short, or both, where two-sided bots carry per-direction books); `market`; `universe` and/or explicit `coins`; `timeframe` (1m to 1d, default 15m); `fresh`; `timing` (hours and days windows in UTC); `entry` (condition tree); `exit`; `sizing`; `filters`; and an optional `feed` block (staleness gate) with `thesis`. `parse()` validates the spec and stamps `_lookback`.

**Condition tree** (`core/expr.py`): groups (`AND`, `OR`, `NOT`) over comparisons (`gt`, `ge`, `lt`, `le`, `eq`, `ne`, plus `crosses_above` and `crosses_below`). Operands are:

- constants;
- indicator references `{ind, params, offset}`, where offset reads committed history (offset −1 is the previous bar);
- cross-series references, where an optional `tf` or `symbol` on an indicator operand reads another timeframe or instrument, causally aligned;
- arithmetic operands `{op: add|sub|mul|div, left, right, offset}`, expressing spreads and ratios without dedicated indicators; division by zero yields None, rendering the condition false;
- feed operands `{feed: social|news, field: score|confidence, offset}`, reading an off-engine scored event series, causally aligned and freshness-masked. No other surveyed platform provides this.

**Indicator registry** (`core/indicators.py`): 216 entries. Coverage includes price and volume series; the full TA-Lib standard set (RSI; EMA, SMA, WMA, DEMA, TEMA, KAMA, HMA, ZLEMA; MACD; Bollinger Bands; ATR and NATR; ADX; CCI; MFI; Stochastic, Stochastic RSI, KDJ; SAR; Supertrend; Donchian; Keltner; the linear-regression family; OBV; VWAP and VWMA; approximately 60 candlestick patterns; fractals; Heikin-Ashi); custom engine indicators (ROC as a fraction, VOL_RATIO, WICK_FRAC, CLOSE_POS, RVOL); and feed series.

**Exit block** (`core/params.py`): `time_bars` (maximum hold); `stop.mode` in `{none, hh, dstop, sig}` with window and param (`trail` mode is deprecated and non-functional); `take_profit` with `tp_close`; `trailing.{k, natr}` (NATR-multiple trailing); and `limit` (resting limit entry).

**Sizing**: `risk` (fraction), `notional_cap`, `weight`, and optional `confidence_scale` (sizing by feed confidence).

**Evaluation semantics**: bar-close evaluation over closed candles; memoized indicator series (`cache`); gapless-guard lookback. Fills occur at a bar close — the signal bar's close by default, or the close of bar `i+d` when `entry_delay=d` models latency. Section 8.1 specifies the next-open fill mode required for import verification parity.

## 5. Import pipeline

The pipeline is singular; languages are adapters. The format is the intermediate representation: multiple frontends, one representation, one runtime.

```
source --> detect --> lint --> translate --> validate --> report --> verify
            (lang)    (capability  (LLM or     (core.       (shared    (trade-list
                      flags)       parser)     strategy.    report)    diff)
                                               parse())
```

**Detect.** Classify the pasted source. Signatures are unambiguous: `//@version=` indicates Pine; `#property` or `OnTick()` indicates MQL; `:step` or `wt-cash-` (EDN or JSON) indicates a Composer symphony; `AddOrder(` or `plot ` indicates thinkScript; `Inputs:` or `SetStopLoss` indicates EasyLanguage; `ApplyStop(` or `Buy =` indicates AFL; `OnStateChange` indicates NinjaScript; a native spec JSON routes directly; anything else is treated as plain English (the additional language, with an empty linter, since `parse-strategy` is itself an adapter).

**Lint.** Per-language static rules emit into the shared capability taxonomy (Section 6), producing a translatability report before any translation. Linting is inexpensive (pattern classification rather than full parsing), is surfaced to the user ("this script is 92% translatable; the remaining 8% is listed below"), and is the telemetry source for roadmap decisions.

**Translate.** Two mechanisms by source type:

- Deterministic parsers where the source is already structured data: Composer (full schema available) and native spec JSON.
- Language-model translation for scripting languages: a per-language system prompt and few-shot examples, with a generate-validate-retry loop following the established `parse-strategy` pattern. The validation gate is the actual `core.strategy.parse()` (exposed through a runtime endpoint), not a prompt-side description of the schema.

**Validate.** `parse()` accepts or rejects with a reason. Nothing unvalidated proceeds.

**Report.** One shared component serves every entry point and presents what mapped, what mapped with notes (for example, `crossover` to `crosses_above`, or `security(4h, close[1])` to a 4h timeframe reference), and what was dropped and why (taxonomy flag plus plain-language explanation). Applying a translated strategy requires viewing the report. The pipeline never approximates silently: it translates what maps, shows what was dropped, and requires confirmation. Partial results carry `{"partial": true}`, following the precedent in `core/mapping.py`.

**Verify.** The imported strategy enters the existing build flow (Compose, Training, Trials, Weather, Deploy); the Training backtest is where verification occurs. The pipeline displays the trade list and, where the source platform provides an export (Pine CSV, MT4/MT5 HTML, TradeStation Excel), offers an upload-and-diff. A match produces a verified-import marker carried onto the bot and its leaderboard entry. Divergence on realtime bars frequently indicates repainting in the original and is treated as explanatory rather than erroneous.

### 5.1 Entry points

All entry points converge on the same apply-spec-and-report step in Compose.

1. **Compose as universal intake.** Pasted content is classified by the detect step and routed accordingly, with no mode selection required.
2. **Explicit import affordance.** A discoverable control with file-drop for `.pine`, `.mq4`, `.txt`, and symphony JSON. Intake is paste-only; the pipeline does not fetch from source platforms, in keeping with their terms of service (TradingView in particular).
3. **Assistant.** The conversational path, and the appropriate place to negotiate dropped semantics (for example, "this script uses pyramiding=3; this can be approximated with a larger single entry, or dropped").
4. **MCP tool `import_strategy(source)`.** Language-agnostic by design, allowing an agent to port a user's full library in one session.

A single edge function (`import-strategy`) serves all entry points, as a sibling to and eventual superset of `parse-strategy`.

## 6. Capability taxonomy

Every linter emits into this shared vocabulary, and every downstream surface (report UI, assistant negotiation, analytics) is built against it. Adding a language does not require changes to downstream code.

| Flag | Meaning | Disposition |
|---|---|---|
| `indicator-condition` | comparisons over registry-expressible indicators | translate |
| `crossover` | cross semantics | translate (`crosses_above`/`crosses_below`) |
| `multi-timeframe` | higher-timeframe references with constant arguments | translate (confirmed-bar semantics, Section 8.3) |
| `cross-asset` | other-symbol references | translate (`symbol` operand) |
| `static-exit` | stop-loss or take-profit fixed at entry | translate (exit block) |
| `trailing-exit` | engine-managed trailing or breakeven | translate (exit primitives, Section 9.1) |
| `time-exit` | maximum-hold or bars-since-entry close | translate (`time_bars`; pattern-match the source idiom) |
| `risk-sizing` | equity-percentage or risk-per-trade formulas | translate (pattern-match `(equity·risk%)/(entry−stop)` to `sizing.risk`) |
| `entry-price-ref` | exits referencing entry price | translate (exit block only, never entry) |
| `param-input` | tunable inputs | translate (params; ranges as metadata, Section 9.2) |
| `event-memory-bounded` | barssince, valuewhen(0), confirmed pivots | translate if Section 9.2 primitives are adopted; otherwise flag |
| `ranked-selection` | top-N by metric (Composer filter) | flag; translate if Section 9.2 is adopted |
| `portfolio-weighting` | weighting or rebalancing nodes | flag (out of scope for v1; documented) |
| `custom-indicator-math` | indicator not in the registry | flag; route to the registry request queue |
| `stateful-logic` | variable latches, counters, flags, strategy-level recursion | reject (P4) |
| `loops-arrays` | loops, arrays, matrices, user-defined types, custom stateful functions | reject (P1) |
| `intrabar-eval` | tick or intrabar execution (varip, calc_on_every_tick, IOG true) | reject (P2) |
| `order-management` | grid, martingale, averaging, pyramiding, partial closes, raw orders | reject (Section 9.3) |
| `lookahead` | future-reading constructs (lookahead on without offset, etc.) | reject and explain |
| `external-io` | news calendars, files, DLLs, network access | reject (feed operands may cover specific cases) |

Every import's flags are logged. The resulting distribution is the roadmap: it distinguishes a gap closable by adding one central indicator from a format ceiling adopted deliberately.

## 7. Export

Export is the reverse direction and is the simpler one. Import contends with a language ceiling (an expressive source lowered into a constrained target, which is lossy and requires linting and rejection). Export does not: everything StratIR can express has a representation in Pine, MQL, and comparable languages, because those languages are supersets of what StratIR permits. Export is therefore deterministic, template-based code generation and requires no language model, since the input is controlled and the emitted idioms are chosen.

Export operates at two levels:

1. **Strategy-level export (code generation).** StratIR to Pine Script, thinkScript, MQL, EasyLanguage, or AFL source. A comparison becomes `ta.crossover(...)`; the exit block becomes `strategy.exit(stop=, limit=, trail_...=)`; a `tf` operand becomes `request.security(expr[1], lookahead_on)` (the non-repainting pattern, emitted by construction); sizing maps to the target's quantity model through the instrument metadata of Section 8.4, in reverse. This supports a "build once in Paper Fleet, export to run on TradingView or MetaTrader" capability and directly addresses lock-in concerns.
2. **Signal-level egress.** Emitting TradersPost-schema webhook JSON (`ticker`, `action`, `quantityType`, `takeProfit`, `stopLoss`, and related fields), the de facto signal-interchange format. This is how a running StratIR strategy reaches a broker; it is signal-level, not strategy-level.

Two constraints apply:

- **Round-trip is not identity, by design.** Importing Pine to StratIR and exporting back to Pine yields cleaned Pine, not the original, because repainting constructs, `varip`, and hand-rolled state were dropped on import (Section 6 rejects). The guarantee is equivalent, deterministic round-trips, not byte-identical ones. The de-risking is a feature, not a defect.
- **Export reopens determinism on the destination runtime.** Once generated Pine runs on TradingView, that engine evaluates it, with its own fill model and repainting surface, so an exported strategy's track record is no longer verifiable by Paper Fleet. The governing position, stated plainly to users, is that import and local execution are verified, while export elsewhere is portability at the user's own risk. Export demonstrates that StratIR is not a lock-in mechanism, which is the required posture for an open standard.

## 8. Engine alignment for verification parity

**8.1 Canonical import fill rule.** A signal at the close of bar N fills at the open of bar N+1. This is the semantic shared by every surveyed platform (the Pine broker emulator default, EasyLanguage with IOG false, thinkScript `open[-1]`, AFL trade delays, NinjaScript on-bar-close, and new-bar-gated MQL). It must be implemented as a new spec-level fill mode (`fill: next_open`); imported strategies require it, and native bots retain current behavior. This is net-new work: the current engine fills at a bar close, not a bar open. By default (`entry_delay=0`) `backtest()` enters at the signal bar's close (`candles[i]["c"]`); `entry_delay=d` moves the fill to the close of bar `i+d` (`core/backtest.py`), which models ingest-and-score latency and is orthogonal to the next-open rule rather than a substitute for it. Without the next-open mode, every verification diff fails by one close-to-open gap per trade.

**8.2 Warm-up parity.** EMA and RMA-family indicators (including RSI, ATR, and ADX internally) are recursive and SMA-seeded on the source platforms, so early trades depend on where history begins. The engine must replicate SMA seeding and enforce a warm-up window (approximately four times the period converges within floating-point noise) before the first evaluated bar of a verification run.

**8.3 Multi-timeframe binding.** The `tf` operand reads the last closed higher-timeframe bar, equivalent to Pine's canonical non-repainting `security(expr[1], lookahead_on)` pair. Scripts using raw unconfirmed higher-timeframe reads are translated to confirmed semantics, with the behavior change noted in the report.

**8.4 Instrument metadata for unit conversion.** Tick size, point value, and minimum lot per instrument are required (extending `core/markets.py` and the instrument tables). Pine exit distances are denominated in ticks, EasyLanguage in dollars, and MQL in pips. A silently mis-scaled stop is the most severe import defect class; conversion must be exact or the import is rejected.

**8.5 Intrabar-fill handling.** Source platforms fill stops and take-profits intrabar along an assumed OHLC path, whereas a bar-close engine fills later and looser. Two options exist: adopt the same documented OHLC-touch approximation for stop and take-profit fills, or verify only entry signals tightly and label exit-fill divergence as expected. The choice is made once and stated in the report component; tick-level equivalence is never implied.

## 9. Format evolution

### 9.1 Required additions

1. **`fill: next_open` mode** (Section 8.1). Blocking for all verification.
2. **Instrument tick and point metadata** (Section 8.4). Blocking for Pine, EasyLanguage, and MQL exit translation.
3. **Return-space indicators.** The registry's one material gap; price-space coverage is already complete (Supertrend, SAR, Stochastic, Donchian, Keltner, HMA, linear regression, and fractals all exist). Required additions: `MA_RETURN` (moving average of returns), `STDDEV_RETURN` (volatility of returns), and `MAX_DRAWDOWN` (windowed). `cumulative-return` approximates to the existing `ROC`. These are four small, windowed, deterministic functions, and they constitute half of Composer's entire condition vocabulary.
4. **Exit-block completion: breakeven and fixed-distance trailing.** NATR-multiple trailing (`trailing.{k, natr}`) exists. Required additions: `BREAKEVEN` (move the stop to entry at a specified gain) and a fixed-percentage or fixed-distance trailing variant, matching Pine's `trail_points`/`trail_offset` and EasyLanguage's `SetPercentTrailing`/`SetBreakEven`. These named primitives absorb the majority of variable-based state in otherwise clean scripts across every source language, and represent the highest-leverage improvement to translation coverage.

### 9.2 Candidate additions (each consistent with P4)

1. **Ranked selection.** A bounded form of Composer's `filter`: rank a universe by a metric over a window and enter only the top or bottom N. Deterministic, declarative, and compatible with the bot model. The boundary is drawn before weighting and rebalancing; full allocation is a separate product and is recorded as out of scope under the `portfolio-weighting` flag rather than partially implemented.
2. **Sample-and-hold operand.** `valuewhen(cond, source, 0)`: the value of a source at the most recent bar where a condition held. An engine-owned latch with a declared trigger. This enables support/resistance strategies and pairs with the existing `FRACTAL_swinghigh` and `FRACTAL_swinglow` indicators.
3. **Bars-since condition.** "The condition held within the last N bars." Bounded event memory enabling the setup-then-trigger two-stage entries common in thinkScript and EasyLanguage.
4. **Parameter-range metadata.** Specs may carry declared sweep ranges (for example, `param fast: 6..24`) as metadata rather than logic, preserving author tuning intent on import (EasyLanguage Inputs, QuantPilot `opt`) and feeding `core/sweep.py`.
5. **Multi-level take-profit.** At most two declared take-profit levels at fixed fractions, engine-managed. Anything beyond this is order management and is rejected.

### 9.3 Excluded constructs

1. **General mutable state** — user variables, counters, flags, and strategy-level recursion. These violate P4. Every surveyed platform that permits them exhibits the same failure pattern: repainting, unverifiable backtests, and persistent support burden. Legitimate uses are absorbed as the named primitives of Sections 9.1 and 9.2.
2. **Tick and intrabar evaluation** — `varip`-class constructs and per-tick logic. These are intrinsically unreproducible, since no two tick feeds match and historical tick data does not exist. Admitting them would break the determinism guarantee (P2).
3. **Grid, martingale, averaging, pyramiding, and partial-close order management.** This is the dominant commercial pattern in the MQL ecosystem and is prohibited by proprietary-firm rules as a category. The untranslatable residue functions as adverse-selection filtering: these strategies produce smooth equity curves masking tail risk and would degrade a verified leaderboard. The inability to express them is a quality control.
4. **Any escape hatch or custom-script node.** This is the recurring request, since every rejected import prompts it. Admitting arbitrary code into a spec reintroduces the sandboxing problem and forfeits determinism and analyzability, reducing the standard to a JSON wrapper around code. The relief valve is the registry (P6): constructs are requested, then added centrally, reviewed, and versioned.
5. **Silent approximation during import.** A pipeline rule rather than a format feature: translate what maps, show what was dropped, and require confirmation. A user discovering after a loss that the imported strategy does not match the original is the specific failure the architecture exists to prevent.

## 10. Verification system

- **Shared diff harness.** Both sides are normalized to `(entry_ts, exit_ts, side, price, qty, P&L)` and diffed with per-platform tolerances: tight on signal timestamps and direction, looser on exit fills (per the Section 8.5 decision), and never on run-up or drawdown, which are intrabar-dependent on the source platforms.
- **Per-platform ingest.** Pine List-of-Trades CSV (carrying rule identifiers through the Signal column and normalizing the chart timezone); MT4 HTML and MT5 HTML/XML tester reports; TradeStation Excel; the Composer backtest API; and thinkScript by re-simulation only.
- **Outcome.** A match produces a verified-import marker on the bot; divergence produces a classified explanation (fill timing, warm-up, repainting in the original, or intrabar exits). The repainting case is a demonstration point: the Paper Fleet result is the deterministic one.
- **Continuous integration.** The Traders' Tips cross-language set and `pyne-in-the-wild` serve as regression suites for the adapters.

## 11. Open-standard plan

- **Publication.** The specification document (Section 4 plus a formal JSON Schema generated from `parse()`), under a permissive license for the schema and specification while the engine remains proprietary, in a public repository with explicit versioning (`spec/v1`) and changelog discipline. The schema ships with validators, specifically the endpoint used by the pipeline.
- **Conformance.** A valid StratIR spec is one that passes the published schema and reference validator. Determinism semantics (bar-close evaluation, causal alignment, fill modes) are normative text, not schema alone.
- **Marketing and copy.** Claims of honesty are not used; verifiability is demonstrated instead (re-derivable track records, verified-import markers, a public spec). The demonstration carries the message.
- **Acknowledged costs.** An open standard entails versioning discipline, an ongoing public surface, and third parties running the format elsewhere. These are accepted: the moat (verification, track records, the fleet, and feed data) is strengthened by adoption rather than threatened by it.

## 12. Build order

1. **Engine groundwork** — `fill: next_open` mode, instrument tick and point metadata, and warm-up parity (Section 8; small and blocking).
2. **Pipeline skeleton and taxonomy** — detect, lint, and report types; the shared report component; the `import-strategy` edge function invoking the real `parse()` gate; and telemetry.
3. **Composer adapter** — a deterministic parser against the known schema, plus the four return-space indicators (Section 9.1). This is a days-scale task, it validates the architecture, and it addresses the orphaned Composer crypto users.
4. **Exit primitives** — breakeven and fixed-distance trailing (Section 9.1), raising translation coverage for all subsequent adapters.
5. **Pine adapter** — the linter (full flag coverage), the language-model translation prompt, and the verification CSV diff; shipped with the `pyne-in-the-wild` regression suite.
6. **thinkScript adapter** — a light linter and prompt, positioned around providing execution to strategies that are simulation-only on thinkorswim.
7. **MCP `import_strategy` tool and specification publication** — the standard is published with three languages of installed base established.
8. **EasyLanguage and AFL adapters** — low-cost once the pipeline is proven, using the Traders' Tips set for testing.
9. **MQL adapter** — last, justified by telemetry, and limited to the simple-EA subset.

The stage 2 linter is independently shippable as a free script-checking tool. It carries no language-model cost and measures which constructs real users require before further investment.

## 13. Competitive context

- **3Commas QuantPilot.** The same thesis (English to DSL to deterministic backtest to deployment), in crypto, with a closed format and Hyperliquid-gated execution. This confirms the architecture as an emerging consensus. Differentiation: multiple markets (crypto perpetual and spot, equities, FX), feed operands, an open standard, and verified imports.
- **Composer (SoFi).** The declarative-tree incumbent, equities-only after ending crypto support in January 2026, with a format now corporately held. Its MCP server demonstrated that agents paired with declarative JSON work; its orphaned crypto users are the first adapter's opportunity.
- **TradingView and MetaTrader.** Corpus incumbents structurally unable to follow, given imperative languages, two decades of accumulated inertia, and repainting and tick-dependence built into their models. In this plan they are sources, not competitors.
- **Interchange ownership.** No party owns strategy interchange today. TRADE.md is defunct, LEAN configuration is not strategy logic, and TradersPost is signal-level only. The position is open.
