# hl_bot — Hyperliquid execution bot (ts30 system)

The production bot from the research. Signals from Binance 15m data
(identical to every backtest), execution on Hyperliquid, strategy ts30:
regime dial < 0 → exhaustion short; dial > +2% → momentum long; else flat.
Full-span backtest 2023–26: +1.75%/trade, +48.7% compounded, positive every
year, worst dd −8.5% (`reports/regime_findings.md`).

## Current state

Running as a **dry-mode daemon** (simulated fills, real signals, real dial).
It is the same code path as live minus order placement — this is the soak
test. Status:

```
python3 hl_bot.py --status
tail -f bot/bot.log
```

## Going live — the arming checklist

The bot refuses live mode unless ALL of these are true:

1. `HL_ACCOUNT` env = your main wallet address (0x…)
2. `HL_PRIVATE_KEY` env = an **API wallet** key (create at
   app.hyperliquid.xyz → More → API — never the main wallet key; API wallets
   can trade but cannot withdraw)
3. `bot/ARMED` file exists containing exactly `YES`
4. started with `--live`

```
export HL_ACCOUNT=0x...
export HL_PRIVATE_KEY=0x...
echo YES > bot/ARMED
pkill -f hl_bot.py
nohup python3 hl_bot.py --live >> bot/nohup.out 2>&1 &
```

Sizing in live mode is capped by `EQUITY_CAP` (default **$1,000** sizing
equity) and `MAX_NOTIONAL_USD` (default **$250** per trade) regardless of
account size. Raise them only deliberately:
`EQUITY_CAP=5000 MAX_NOTIONAL_USD=500 nohup python3 hl_bot.py --live ...`

`--short-only` runs the gate30 book alone (lowest-drawdown configuration).

## Risk stack (all active in live mode)

| layer | rule | action |
|---|---|---|
| per trade | 0.75% of sizing equity / stop distance, ≤20% equity, ≤$250 | position size |
| stop | resting stop-market on HL at the research stop level, reduce-only | survives bot death |
| concurrency | max 6 positions, 1 per coin | skip entries |
| research kill-switch | 7d equity dd < −5% | pause entries 3d |
| daily breaker | 24h dd < −5% | close everything, halt 24h |
| weekly breaker | 7d dd < −12% | close everything, full halt — writes `bot/HALTED`, manual delete required |

## What to watch in the first live week

- **Fills vs signal price** — the untested assumption in the whole research
  stack is mania-moment slippage. `bot/trades.csv` records entry fills;
  compare against the Binance close in the log line. If entry slippage
  averages worse than ~0.3%, the edge math changes (backtest survives 4×
  costs, so there's margin — but measure it).
- **First stop execution** — verify on the HL UI that the resting stop
  appears after the first entry, and that it's gone after the exit.
- **Funding** — shorts pay/earn funding on HL; 4h holds make it small but
  it's unmodeled. The equity curve in state.json captures it implicitly
  (live equity = account value).

## Known limitations

- Signals pause when the Mac sleeps; open positions are protected by the
  on-exchange stop, and exits replay on wake. Time exits fire late after a
  sleep — acceptable for 4h/12h holds, but a always-on box (VPS) is the
  right home for live.
- Binance is the signal source; an HL-listed coin that Binance delists goes
  dark for signals (the 60-coin universe is Binance-verified today).
- The ts30 configuration was finalized today after seeing full-span results
  (dial window, +2% long threshold, momo anatomy). Per the project's own
  discipline: the paper fleet and this dry soak are the out-of-sample test.
  The defensible path is dry/paper until the ~2-month checkpoint, then
  micro-live with these default caps.
