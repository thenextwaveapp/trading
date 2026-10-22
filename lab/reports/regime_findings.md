# Regime dial findings — 2026-10-05

Two experiments (`regime_switch_backtest.py`, `regime_policy_test.py`) on the
full continuous span 2023-01 → 2026-10 (both candle caches concatenated,
boundary 2024-12-15, no gap). Same signal, fees, sizing, kill-switch as the
fleet. Short-arm reimplementation verified: reproduces the pre-registered 74
trades at +3.407% exactly.

## Finding 1 — window selection bias in the headline number

The pre-registered +3.41%/trade was measured on 7 windows of ~45 days
covering only ~54% of Mar 2025 → Oct 2026. The gaps between windows had never
been tested by anything. Result:

|                    | trades | net/trade | median |
|--------------------|--------|-----------|--------|
| inside the 7 windows | 74   | +3.41%    | +1.46% |
| in the gaps          | 74   | +1.08%    | −0.29% |

True full-calendar edge Mar25→Oct26 ≈ **+2.2%/trade**. Still real, still
positive — but the headline was inflated ~50% by window placement luck
(windows inherited from the ML walk-forward, so not deliberate, but luck all
the same). By calendar year, short-only: 2023 −1.39%, 2024 −0.64%,
2025 **+0.54%**, 2026 **+3.97%**. The edge is mostly a 2026 phenomenon, not
"since March 2025".

**Consequence for the paper-fleet checkpoint:** expect base to track ~+2%
/trade, not +3.4%. Do not kill the strategy for "underperforming the
backtest" against the inflated number.

## Finding 2 — the dial works as a gate, not as a flip

Dial = trailing mean 24h forward return of completed pump events
(runup ≥12%/4h, no weakness/vol filter, 24h per-ticker cooldown), strictly
causal. Full-span arms:

| arm | trades | net/trade | compounded | worst dd |
|-----|--------|-----------|------------|----------|
| short-only (fleet today) | 247 | +1.08% | +17.5% | −5.3% |
| flip 30d (long when dial+) | 236 | +1.18% | +20.1% | −3.0% |
| flip 60d | 237 | +0.21% | +4.3% | −5.0% |
| **gate 30d (short/flat)** | 96 | **+2.48%** | +16.1% | **−3.1%** |
| gate 60d | 89 | +1.80% | +8.9% | −3.6% |
| self-gate 60d (own trailing P&L) | 124 | +2.05% | +20.6% | −4.3% |
| self-gate 90d | 134 | +1.81% | +18.4% | −4.3% |

- **Flipping direction is not robust**: brilliant at 30d, terrible at 60d.
  One lucky grid point ≠ a system. Rejected.
- **Gating is robust**: every gate variant (broad-pump 30/60d, self-referential
  60/90d) improves net/trade (+66% to +130%) and worst drawdown vs short-only,
  at roughly the same compounded return with half the trades. The dial's
  value is *staying out of the hostile regime*, not trading the other side.
- The long mirror of this entry is weak even in 2023-24 (+1.8%/+0.7% per
  trade) — the weak-close filter selects pumps that fail, which is a
  short-shaped edge. The 2023-24 "continuation" profit in the OOS report was
  a property of pumps broadly at 24h horizon, not of this entry.

## Finding 3 — why the broad dial and the signal sometimes disagree

In 2026Q3 the 60d broad-pump dial read LONG (pumps on average continuing)
while the filtered signal shorts made +3.96%/trade. The conditional edge
(pumps that print a heavy red candle on 2× volume fade) is more stable than
the unconditional pump regime. This is why self-gate (trailing P&L of the
strategy itself) is the theoretically cleaner dial; broad-pump 30d just
happens to track it well with more sample.

## Deployed

`gate30` added to the paper fleet as a 10th variant: base rule, trades only
when the live dial (30d window, ≥10 completed events, mean < 0) allows.
Event store `paper/fleet/pump_events.json`, seeded from cache
(`seed_pump_events.py`, 81 events). Gate at deploy time: SHORT allowed
(n=72, m=−1.56%).

Not pre-registered — it rides along for the same ~2-month checkpoint. The
honest comparison at checkpoint: gate30 vs base on the same signals
(gate30 skips are logged, so forgone trades are measurable).

## Caveats

- Dial window/threshold chosen in 2026 having seen both regimes. Grid
  sensitivity reported in `regime_switch_*.txt`; gate direction is robust
  across the grid, exact magnitude is not.
- 2023-24 universe is survivor-thin (47 tickers, majors-heavy).
- `flip-30`'s all-four-years profitability is noted and deliberately NOT
  deployed; revisit only if it survives its own pre-registration design.

---

# Addendum — indicator architecture tests (same day, later)

A proposed indicator-heavy spec (BTC guardrails, wick/close-location anatomy,
per-setup win-rate dials, momentum long, panic long) was tested component by
component: `indicator_tests.py`, `twosided_system_test.py`,
reports/indicator_tests_*.txt, twosided_system_*.txt.

## Graded against full-span data (2023-01 -> 2026-10)

| proposed rule | verdict | evidence |
|---|---|---|
| BTC trend guardrail on shorts | **REJECT** | blocks 2/3 of trades, compounded +17.5% -> +3.6%. Confirms robustness sec F: the edge lives in both BTC regimes — BTC indicators do not carry the pump-regime signal. |
| 4h candle-boundary execution | **REJECT** | up to 3h45m delay; delay ladder already showed 1h kills the edge. Keep rolling 15m closes. |
| win-rate>50% dial (vs expectancy) | competitive, slightly more conservative (+2.93%/trade, dd -2.2% vs +2.05%, dd -4.3%; lower compounded). Not wrong, not clearly better. |
| upper-wick >= 30% filter on short | **STRONG** | +3.23%/trade (3x base), win 61%, worst dd -1.5%, 2026: +8.98%. Trades drop to 74/45mo. |
| close-location <= 50% on short | reject | nearly extinguishes the signal (6 trades/45mo) — redundant with the red-close rule. |
| momentum long (strong close, wick<=15%, top-20% close, 2.5x vol) | **KEY FINDING** | +1.88%/trade in 2023, +1.15% in 2024, negative 2025-26. This is the correct continuation-regime entry — the earlier flip failed because it mirrored the weak-close entry. |
| panic capitulation long | park | 6 trades/45mo, +16.2%/trade, 100% win — direction right (matches trader fade behavior) but sample useless. Loosen thresholds in round 2 if desired. |

## The two-sided system (deployed as `ts30`)

dial < 0 -> exhaustion short (weak close); dial > +2% -> momentum long
(strong close, 12h hold); else flat. Asymmetric threshold is essential: at
long-threshold 0 the long book bleeds -3.1%/trade in 2026's brief positive
dial periods; at +2% it clears.

| arm | trades | net/trade | compounded | worst dd | years positive |
|---|---|---|---|---|---|
| short-only | 247 | +1.08% | +17.5% | -5.3% | 2 of 4 |
| gate30 | 96 | +2.48% | +16.1% | -3.1% | 2 of 4 (flat the others) |
| **ts30 (long thr +2%)** | 317 | +1.75% | **+48.7%** | -8.5% | **4 of 4** |

Robust to long-threshold choice (+1%/+2%/+3% -> +44%/+49%/+34% compounded)
and dial window (30d/60d both positive all years at thr 0). Live parity
verified: 50/50 momo and 16/16 short signals reproduce backtest exactly.

## On "indicators" generally

Indicators are state descriptors. Tested here, they split into:
- **Anatomy of the signal candle** (wick, close location) — WORK. They read
  the auction at the moment of the trade: who's trapped at the high.
- **Context indicators** (BTC trend/EMA) — FAIL. The regime variable is how
  pumps *resolve*, which no price-state indicator sees; only outcome
  measurement (the dial) captures it.

Caveat: everything new today (wick filter, ts30, +2% threshold) was chosen
after seeing full-span results. Degrees of freedom are accumulating —
pre-registration round two should freeze: gate30-short (wick30 optional),
ts30 spec, and the +2% threshold, before any real-money decision.
