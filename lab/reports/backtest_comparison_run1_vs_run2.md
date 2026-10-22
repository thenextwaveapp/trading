# Backtest Comparison: Run #1 vs Run #2

Generated: 2026-10-05 07:15 UTC
Sources: `reports/backtest_2026-10-05_0656.txt`, `reports/backtest2_2026-10-05_0711.txt`
Scripts: `backtest.py`, `backtest2.py`

Both runs: same universe (22 tickers), same continuous candle data
(2026-07-15 → 2026-10-04), same calibration window (Aug 1–18), same
out-of-time test window (Aug 19 → Oct 3, 46 days). Nothing about the test
period or data changed between runs. Only the system changed.

## 1. What changed between the runs

| Component | Run #1 | Run #2 |
|---|---|---|
| Training data | 9,448 trader entries only | 10,041 trader entries + 46,446 wild background points |
| Target label | 4h forward return > 0.25% | MFE(2h) ≥ 1.0% AND MFE/MAE ≥ 2.0 (spike, not drift) |
| Regime gate | none | BTC 4h EMA20/50: bull → longs only, bear → shorts only |
| Trend gate | none | skip if ticker ADX(14, 1h) > 30 |
| Entry | market order at 15m candle close | resting limit at candle low + 0.25×ATR15, TTL 30 min, fill only on strict trade-through |
| Exit | fixed 4h hold, market out | TP +1.5×NATR (maker) / SL −1.0×NATR (taker+slip) / time-out 2h |
| Fees modeled | 0.04% / 0.17% / 0.47% round trip scenarios | maker 0.015% per leg; taker 0.045% + 0.05% slip on stop/time legs |
| Same-candle TP/SL conflict | n/a | resolved as SL (pessimistic) |

## 2. Headline results

| Metric | Run #1 (base costs) | Run #2 |
|---|---|---|
| Trades | 1,064 (23.6/day) | 472 (10.5/day) |
| Net per trade | −0.253% | +0.014% |
| Net total over window | −269% (additive) | +6.4% (additive) |
| Hit rate | 47.1% | 44.1% |
| Gross per trade | −0.083% | +0.096% |
| Max drawdown (additive, equal-weight) | −363% | −51.2% |
| Sanity anchor (all scan points) | +0.0000% ✓ | same data ✓ |

Net improvement: ~+0.27% per trade. The system moved from clearly losing
to breakeven-with-noise. It did not move to clearly winning.

## 3. Where the improvement came from

**Direction mix.** Run #1 fired 775 shorts vs 289 longs into a window where
the short-side market baseline was −0.23% per 4h. Run #2's regime gate
flipped the mix to 376 longs vs 96 shorts. This is the largest single
contribution.

**Entry prices.** Run #1 entered at the candle close after the dip —
structurally late for a mean-reversion edge. Run #2 rested limits inside
the dip and only counted fills on trade-through: 674 orders placed, 472
filled (70%). Gross per trade went from −0.083% to +0.096% despite a
*stricter* fill assumption.

**Fees.** Run #2's winners exit at maker rates. Average fee drag per trade
fell from 0.17% (run #1 base scenario) to ~0.06% (blended across exit types).

**Exit engine.** The bracket reshaped the trade distribution rather than
adding net edge by itself:
- TP exits: 164 trades, +1.673% net average
- SL exits: 239 trades, −1.173% net average
- Time exits: 69 trades, +0.179% net average

With a 1.5:1 TP/SL ratio, breakeven needs roughly 43% of resolved trades
to reach TP first. Run #2 achieved 44.1% — one point above breakeven, so
the current result rests on that one percentage point.

## 4. What did NOT improve

- **Shorts still lose**: −0.177%/trade net (n=96) even when only allowed in
  bear regime. Shorts have now been net-negative in every configuration
  tested (run #1, run #2, and the wild scan baseline). Longs alone in run
  #2: +0.062%/trade net.
- **Dispersion is untouched**: ticker totals range from FARTCOIN +13.7% to
  ENA −14.4%; weekly net swings between +25.3% and −21.3%. Equal-weight
  sizing doesn't control this; the additive −51% drawdown shows
  sizing/portfolio logic is still missing.
- **Median trade is negative** (−0.64% net): the strategy is now a
  positive-skew system — most trades stop out small, a minority of TP
  hits provide the profit. With that profile, n=472 is a small sample
  for estimating the mean.

## 5. Caveats that apply to BOTH runs

1. **One 46-day window, one market regime.** Everything above is a single
   sample. A +6.4% result and a −6% result on this window are not
   distinguishable claims about the future.
2. **Threshold and gates were calibrated pre-test, but the run #2 *design*
   (which fixes to apply) was chosen after seeing run #1's test results.**
   Run #2 is therefore a diagnosis-driven iteration, not a clean
   confirmation. Its settings must be frozen and confirmed on windows
   neither run has touched (2025, early 2026).
3. Fill model is candle-based; real queue position and adverse selection
   on limit fills can only be measured live.
4. Funding features were blank in both scans (not fetched for the
   continuous data); the model trained with them present on trader rows.

## 6. Status

- Run #1: system lost −0.25%/trade net. Diagnosed causes: un-gated shorts
  against trend, late market-order entries, positive-only training.
- Run #2: all three causes addressed → +0.01%/trade net. Breakeven.
- The remaining gap between breakeven and a deployable system is unproven.
  Next discriminating test: walk-forward over multiple historical windows
  (data fetchable with existing scripts), with run #2's configuration
  frozen, long-only as a candidate variant evaluated alongside.
