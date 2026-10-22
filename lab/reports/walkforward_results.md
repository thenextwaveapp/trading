# Walk-Forward Results

Generated: 2026-10-05 07:50 UTC
Artifacts: `backtest/ledger_wf.csv.gz`, `backtest/trades_wf.csv.gz`, `backtest/metrics_wf.csv`
Engine: `wf_engine.py` (run #2 config frozen; bracket TP 1.0 / SL 1.5 / hold 8 chosen
on run #2 window fills via `ledger_analysis.py`)

## Setup

7 test windows, Mar 2025 → Oct 2026. Per window: model trained only on trader
entries before the window + 5x wild negatives from the pre-window month;
threshold = p99 of pre-window calibration scans; portfolio layer (0.75% risk
per trade, 20% notional cap, max 6 concurrent, 7-day −5% kill-switch).

Three variants: A (bull→longs, bear→shorts), B (long-only, bull regime),
C (longs in bull; shorts require BTC bear + ticker downtrend).

Gate, registered before the run, scored on W1–W6 only (W7 excluded
because the bracket was selected on its fills):
net/trade ≥ +0.10% · ≥60% windows positive · max DD ≤ 20% · top ticker ≤ 40% of +PnL.

## Results (W1–W6 pooled)

| Variant | Trades | Net/trade | Windows + | Compounded equity | Worst window DD | Top-ticker share |
|---|---|---|---|---|---|---|
| A | 925 | −0.047% | 2/6 | −5.52% | −10.2% | 24% |
| B | 774 | −0.028% | 1/5 | −2.87% | −6.4% | 25% |
| C | 765 | −0.077% | 2/6 | −8.30% | −10.2% | 26% |

Per-window net/trade (variant A): +0.08%, −0.12%, −0.16%, −0.09%, +0.18%, −0.24%.
No variant is consistent across regimes; the positive windows (W1, W5) don't
share an obvious regime property.

W7 (the window the bracket was tuned on): +0.122%/trade, +10.9% equity — all
three variants. Expected, since the configuration was selected on this window;
W7 is excluded from scoring for that reason.

## Gate result

Did not pass (all three variants). Pooled expectancy is negative; 1–2 of 6
windows positive vs ≥60% required. Drawdown and concentration criteria passed.
Per the pre-registered rule, this configuration does not go to micro-live.

## Findings so far

Consistent across every test:
- The traders' timing edge at their own entries: +0.55% vs 0.00% random control,
  across quarters, regimes, traders, and outlier trimming.
- The mixture structure (fade/drift/chase) and exit anatomy findings.
- The ML model ranks quality *among trader-selected moments* out-of-time
  (top quintile +1.29% vs +0.46% baseline).

Did not transfer to the wild:
- Standalone condition-firing. Run #1 (market entries, no gates): −0.25%/trade.
  Run #2 (gates, limits, brackets): ~breakeven on its window; walk-forward
  across 6 fresh windows: −0.03% to −0.08%/trade depending on variant.
- Adverse selection measured on fills: filled orders −0.10% post-signal vs
  unfilled +0.05% — the resting limit preferentially fills on continuing drops.
- Model score adds value only in its top quintile among fills; gates/exits do
  most of the work, and net of costs it isn't enough.

## Interpretation

The traders' edge shows up at their entries, but comes from information not
present in (or not yet extracted from) 15m candle-level market state. Two
extraction attempts plus a bracket-optimized walk-forward did not recover it
net of costs, out of sample.

## Next options

1. Finer data: 1m candles / order-book snapshots around their entries — the
   fade pattern plays out over minutes; 15m may be too coarse.
2. Different target: train on the slow-drift ingredient (C3) with multi-hour
   horizons and maker-only execution, dropping the fade.
3. Different signal source: their *live* entries as an input (+0.5%/trade
   before costs) — but that is copy-trading, a different project than the one
   specified.
4. Stop here. The dataset, pipeline, ledger, and results stand as-is.
