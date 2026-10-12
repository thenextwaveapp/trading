# live/ — the real-money bot

Self-contained go-live package. Two books, one Hyperliquid account:

| Book | Rule | Exit |
|---|---|---|
| `hold24` (SHORT) | run-up ≥12%/4h + first red close + vol ≥2× → short at close · **pump-dial gate**: trades only while the trailing 30d mean 24h fwd return of pump events is < 0 (the dial that kept this leg out of 2023-24) | stop = 4h high, **resting reduce-only stop-market on the exchange** (survives the bot dying); time exit 24h |
| `capit_slow` (LONG) | 24h return ≤ −20% fresh crossing, BTC 4h EMA20≤EMA50 bear gate → long at close | no stop (by spec); time exit 48h; sized on 2×NATR24 |

The bot maintains its own pump-event store (`pump_events.json`, seeded from
the paper fleet's) to drive the dial. **Aggregate exposure cap**: total open
notional never exceeds `max_gross_frac` (100%) of sizing equity — new
entries are trimmed or skipped when the book is full. **Regime monitor**:
the dashboard tracks the short book's stop-out rate over its last 20 trades
(~40% = regime healthy, drifting past ~55% = the edge dying; drawdown depth
is order-luck per the shuffle test, so watch stop-outs, not dd). Sizing
dial-up path: `size_pow` per book scales notional by signal strength
(0 = flat/Monk, the super_larry.py ladder raises it) — change it only with
the spec-change alert in mind.

Signals come from Binance futures 15m candles — byte-identical logic to the
paper fleet (`python3 live/check_parity.py` proves it, run from repo root).
Execution on Hyperliquid (58/60 universe coins listed). The spec lives in
`config.json` and is fingerprinted: any change to the books is logged and
phone-alerted.

## Risk stack (always on)

0.75% equity risk/trade · 20% notional cap · live hard caps **$1,000 equity
/ $250 per trade** (raise in config.json after the 20–30-trade review) ·
max 6 concurrent, 1/coin · kill-switch 7d −5% → 3-day entry pause · daily
breaker 24h −5% → flatten + 24h halt · weekly breaker 7d −12% → flatten +
`live/HALTED` (manual `rm` after review) · `live/PAUSED` stops new entries
· `live/FLATTEN` (dashboard button) closes every position within ~10 s and
halts.

## Modes

Ships in **dry mode**: full pipeline, simulated fills at candle closes with
Hyperliquid-level costs (0.09% round trip), no keys needed. The dry record
in `trades.csv` is tagged `mode=dry` so it never mixes with live rows.

## Setup

```
bash live/launchd/install.sh     # bot (dry) + dashboard, auto-restart, boot-start
open http://localhost:8788
```

## Arming checklist (going live)

1. On Hyperliquid: fund the account with the micro bankroll ($1–2k), then
   create an **API wallet** (Settings → API) — it can trade, it cannot
   withdraw. That key is the only one the bot ever sees.
2. `live/keys.env` (then `chmod 600 live/keys.env`):
   ```
   HL_PRIVATE_KEY=0x<api wallet private key>
   HL_ACCOUNT=0x<main account address>
   ```
3. `config.json` → `"live": true`
4. `echo YES > live/ARMED`
5. `launchctl kickstart -k gui/$(id -u)/com.trading.livebot`
6. **Watch the first trade on the Hyperliquid UI** — the order path (stop
   trigger format, fills) has never run against the real exchange.

All three of keys/config/ARMED are required; missing any one, the bot logs
why and runs dry. Disarm = `rm live/ARMED` + restart.

The first 20–30 live trades are the measurement: compare `mode=live` rows
against the paper fleet's same-signal trades (fills on violent candles,
funding, stop behavior). Size up by raising `equity_cap_usd` /
`max_notional_usd` only after that comparison.

## Moving to a VPS (recommended before arming)

The folder is self-contained: copy `live/` to the box, `pip install
hyperliquid-python-sdk eth_account`, run `python3 bot.py` under systemd
(translate the launchd plist: same command, `Restart=always`). The
dashboard binds localhost — reach it via `ssh -L 8788:localhost:8788`.
No Mac, no lids, no sleep.

## Files

| File | What |
|---|---|
| `bot.py` | the engine (dry/live) |
| `dashboard.py` | http://localhost:8788 — status, positions, controls, flatten |
| `config.json` | the frozen spec + caps (fingerprinted) |
| `universe.json` | 58 HL-listed coins (TON dropped, PEPE deduped) |
| `check_parity.py` | proves signal code == fleet code |
| `state.json` / `trades.csv` / `bot.log` | runtime state, the record, the log |
| `keys.env` | you create this; never commit it anywhere |
| `ARMED` / `HALTED` / `PAUSED` / `FLATTEN` | control flags |
