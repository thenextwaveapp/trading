# Pre-registered rules — pump-short & drift-long (frozen 2026-10-05 08:05 UTC)

Thresholds derived from trader-entry characterization only (no wild data used).
Each rule is tested once on the walk-forward windows, with no iteration
against results.

## Rule P: PUMP-SHORT
Signal at a 15m candle close, any universe ticker:
- 4h run-up: close / close[16 candles ago] − 1 ≥ +12%
- first weakness: current close < previous close
- event volume: current 15m volume ≥ 2× mean of prior 8 candles
- market alive (nonzero volume, gapless last 9 candles)
Entry: SHORT, market at signal close (taker, pessimistic).
Exit: stop if price prints a new high above the signal-time 4h high (taker+slip);
otherwise market out after 16 candles / 4h (taker+slip).
No regime gate (their pump-shorts span regimes).

## Rule D: DRIFT-LONG
Signal at a 15m candle close:
- BTC 4h EMA20 > EMA50 (bull regime)
- quiet tape: |close/close[4] − 1| < 1% and |4h return| < 3%
- mid volatility: 0.8% ≤ NATR(24h,1h) ≤ 2.5%
Entry: LONG, market at signal close (taker).
Exit: market out after 96 candles / 24h; safety stop 3× NATR24 (taker+slip).
Additional requirement: must beat an always-long baseline (same tickers, same
windows, random entry times, same hold) by ≥ +0.10%/trade — otherwise it is
just long exposure.

## Shared
Portfolio: one position per ticker, max 6 concurrent, 0.75% equity risk sizing,
20% notional cap, kill-switch 7d −5% → 3d pause. Fees: taker 0.045%/leg + 0.05%
slip on stop/market exits.
Windows: the same 7 walk-forward windows (Mar 2025 → Oct 2026).
Universe: top ~60 Binance-futures tickers by Invo trade count (pump-shorts
occur on small caps; the 22-ticker universe missed them).

## Gate (pass → micro-live candidate; fail → stop)
- pooled net/trade ≥ +0.10% (rule D: additionally beat the always-long baseline by +0.10%)
- ≥ 60% of windows net-positive
- compounded max DD ≤ 20%
- no ticker > 40% of positive PnL

## Rule change, made 2026-10-05 08:40 UTC — before the pump-short test was run
The pump-short only trades when a pump happens, so some test periods may have
few or no signals. A near-zero result from a period with almost no trades
says little either way.

Updated consistency check, pump-short only: periods with fewer than 10 trades
are excluded from the 60%-positive check; it applies only to periods where the
rule actually traded. (10 is a judgment call: below that, a period's result is
mostly noise.)

Everything else is unchanged: net per trade, drawdown, and ticker-concentration
checks stay as written above.

This change is timestamped because test changes only count if made before
seeing results. It was made before the pump-short data finished downloading.
The drift-long had already not passed under the original rules; that result
stands unchanged.
