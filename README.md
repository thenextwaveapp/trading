# Trading

Updated: 2026-10-11. Single source of truth (old `reports/HANDOFF.md` merged in).

## What this is

Mined 15,713 trades from 52 top Invo traders (Feb 2024 → Oct 2026), found
the market conditions behind their entries, trade the setup on Hyperliquid
— not copy-trading. Result: a paper fleet of strategy variants (short and
long books — see `fleet_config.json`) derived from their conditions, each
earning its own live verdict.

## Rule P (frozen) — the short book's base rule

On 15m candles, short at candle close when ALL hold:

1. `close / close[16 bars ago] − 1 ≥ 12%`  (4h stretch)
2. `close < prev close`                     (first red candle)
3. `volume ≥ 2× mean of prior 8 bars`       (event volume)
4. market alive (gapless 4h, nonzero vol, high ≠ low)

Stop = max high of the signal 4h window. Time exit 4h. Taker fees + slip
(0.045%/leg + 0.05%). Size = min(0.75% equity / stop-distance, 20% equity).
Max 6 concurrent, 1/ticker. Kill-switch: −5% equity in 7d → 3d pause.

Expectation: ~+2%/trade, ~2 trades/week, ~53% win (2025–26 full calendar;
walk-forward windows gave +3.41%). Dashboard benchmark in `fleet_config.json`.

## The 60-ticker universe

`paper/universe60.json` = the tickers the 52 Invo traders traded most
(Feb 2024 → Oct 2026), mapped to Binance perps.

## Findings

1. Trader entry timing is real: +0.55%/4h vs 0.00% random, ~13σ, robust
   across quarters/regimes/traders. Their exits capture ~30% of the move.
2. ML extraction failed out-of-sample twice (−0.03 to −0.08%/trade). The
   edge is in trade selection, not averaged features. (`walkforward_results.md`)
3. Reading individual trades found the phenomenon: their big wins are
   shorts into parabolic small-cap pumps.
4. Rule P passed a pre-registered gate: 74 trades, +3.4%/trade, all 7
   windows positive, CI [+1.2, +5.9]%. (`rules_preregistration.md`)
5. Edge scales with pump size (8% → +0.86%, 12% → +3.41%, 16% → +6.46%)
   and volume filter.
6. Edge persists to 24h hold, gone by 48h; stop choice barely matters.
7. Robustness battery: monotone in thresholds, survives 3–4× costs, beats
   placebos, LOO-stable. Entry is perishable: 15-min delay halves the
   edge, 1h removes it — taker entry at close. (`pump_short_robustness.py`)
8. Full-calendar edge ≈ +2.2%/trade (2025: +0.54%, 2026: +3.97%); the 7
   walk-forward windows covered only ~54% of the span. (`regime_findings.md`)
9. In 2023–24 the same signal lost (−0.8%/trade); regime flipped ~early
   2025. The regime dial exists because of this. (`oos_backtest_*.txt`)
10. Dial (trailing 30d mean 24h fwd return of pump events): robust as a
    short/flat gate (+2.48% vs +1.08% ungated), not as a direction flip.
    Two-sided (dial<0 short, dial>+2% momo long) positive all 4 years.
11. 2026-10-11, era20 cache (2020–22, 166 perps): dial tracks regimes
    correctly (2021 pinned long, flipped short H2 2022); tuned-up sizing
    loses out-of-regime even gated. (`era20_test_*`)
12. 2026-10-11, wide cache (every USDT perp ever, 900): edge is
    universe-specific — full universe ≈ breakeven, placebo-60 and random-60
    universes lose. (`wide_veto_test_*`, `placebo_universe_*`, `random_degen_*`)
13. 2026-10-11: point-in-time universe rebuild (trailing Invo trade count,
    no hindsight) cuts tuned-sizing results ~1000×. Static-universe
    backtests overstate; judge on live fleet results. (`pit_universe_*`)
14. 2026-10-11: `veto` (skip entry when dial > +2%) passed its OOS test:
    +2.49% vs base +1.95%, same dd. Failed-high confirm failed — drops
    winners. (`veto_fh_test_*`)

## Variant provenance

`base` is the pre-registered original. Everything else came from later
research rounds; each gets its live verdict from its own paper account.

## Live paper fleet

`paper_fleet.py` — one process, 15m cadence, Binance futures data,
60-ticker universe, one $10k paper account per variant. Signal/exit code
reproduces backtest trades (pump-short 74/74, capit-long 1667/1670).

Config: `fleet_config.json`. `ops` = port, benchmark, alert toggles — edit
freely. `strategies` = all variants and params, one note each; the fleet
fingerprints params on start and alerts on change. `"enabled": false`
parks a variant. The strategies section is the authoritative lineup;
dashboard groups by direction (short / long / both).

```
http://localhost:8787                    # web dashboard (fleet_dashboard.py)
python3 paper_fleet.py --status          # terminal dashboard, one-shot
python3 paper_fleet.py --monitor         # terminal dashboard, live
bash launchd/install.sh                  # install fleet + dashboard as
                                         # launchd agents (auto-restart)
```

Dashboard: health banner, P&L cards, open positions marked to live
prices, equity curves, variants vs backtest, trades, pump events, log
tail. Controls (this Mac only; `--lan` = read-only phone viewing):
start/stop/restart, pause (`paper/fleet/PAUSED` — stops new entries,
keeps managing open ones), keep-awake.

Phone alerts (ntfy): entries/exits, kill-switch, errors, pause, fleet
down/up. Config `paper/fleet/ntfy.json`; topic string works like a
password.

Lid-shut: keep-awake toggles `pmset disablesleep` (one-time
`sudo bash launchd/allow_pmset.sh`). While ON the Mac never sleeps; OFF =
sleep pauses scanning, open positions replay on wake.

2026-10-10: unknown CLI args exit with an error; `paper/fleet/fleet.lock`
prevents a second instance; tmp files per-PID.

### Live results

- ALGO short, Oct 8: base +11.3%, slow +15.8%, hold24 +14.0%, fast +2.6%;
  all 11 participating variants won; wick30 didn't fire.
- `hl_bot.py` (ts30 port, 58/60 coins on HL) runs as a dry daemon —
  runbook `bot/README.md`.

## Path to real money

1. 2–4 weeks paper (~10+ base trades) vs the configured benchmark.
2. Regime monitor: stop-out rate drifting 40% → 55% = regime dying.
3. Pre-registration round 2: freeze the go-live variant spec.
4. Hyperliquid wallet, micro size $1–2k, 0.75% risk, kill-switch live.
   20–30 live trades before size-up.
5. Pump-short entry: taker at close within 30s, not postOnly. Capit-long
   is delay-tolerant; limit entries fine there.

## Folder map

| Path | What |
|---|---|
| `Invo/` | raw scrapes: users, portfolios, trades |
| `bn/` | Binance data pullers + candle/funding data for trader analysis |
| `master/` | consolidated trades master (15,713), feature matrix, labels |
| `backtest/` | candle caches (era20 2020–22, oos 2023–24, r60 2025–26, wide 900-perp) + ledgers |
| `reports/` | all analysis output, timestamped |
| `research/` | all analysis/backtest/fetch scripts — run from repo root: `python3 research/<script>.py` |
| `logs/` | old one-off fetch/run logs |
| `paper/` | paper trading state: universe, per-variant state, trade logs |
| `bot/` | hl_bot state + runbook |
| `live/` | go-live package: hold24 short + capit_slow long on Hyperliquid, dashboard :8788, dry until armed — `live/README.md` |
| `launchd/` | launchd agents + installer |

Root keeps the live-side code (`paper_fleet.py`, `fleet_dashboard.py`,
`paper_trader.py`, `hl_bot.py`, `fleet_config.json`); launchd and `live/`
import from here. Scripts moved to `research/` 2026-10-11;
`variants_backtest`, `oos_backtest`, `seed_pump_events` carry a 2-line
path shim to reach root.

Scripts, roughly chronological (all in `research/`):

| Script | What |
|---|---|
| `eda_report.py` | exploratory analysis of the trader dataset |
| `build_feature_matrix.py` | market-state features at each trader entry |
| `cluster_paths.py` | forward-path clustering |
| `classifier_test.py` | ML entry-quality model, out-of-time test |
| `backtest.py` / `backtest2.py` | ML condition-firing backtests (failed) |
| `wf_engine.py` | walk-forward engine + portfolio layer (constants) |
| `rules_backtest.py` | pre-registered rules P and D |
| `variants_backtest.py` | entry-parameter variants |
| `holds_stops_backtest.py` | hold-horizon and stop-style sweep |
| `robustness_backtest.py` | delay ladder, cost stress, random control |
| `pump_short_robustness.py` | 23-variant stress battery |
| `oos_backtest.py` | 2023–24 out-of-sample run |
| `regime_switch_backtest.py` | full-span regime-dial backtest |
| `regime_policy_test.py` | dial policy comparison |
| `indicator_tests.py` | indicator/anatomy/BTC-guard audit |
| `twosided_system_test.py` | two-sided regime system |
| `seed_pump_events.py` | seed the live gate's event store from cache |
| `fetch_*_data.py` | candle fetchers (Binance Vision archive) |
| 2026-10-10/11 round | `degen_derby`, `exits_lab`, `derby_heats`, `larry_tuner`, `grand_finale`, `soft_gate`, `super_larry(+_wide)`, `era20_test`, `dial_persistence`, `veto_fh_test`, `wide_veto_test`, `pit_universe_test`, `random_degen`, `fetch_mega_data` — sizing/exit/universe experiments, see docstrings |

Live-side code:

| Script | What |
|---|---|
| `paper_fleet.py` | the paper fleet |
| `fleet_config.json` | ops settings + fingerprinted strategy definitions |
| `fleet_dashboard.py` | web dashboard, http://localhost:8787 |
| `hl_bot.py` | Hyperliquid execution bot (ts30), dry/live |
| `paper_trader.py` | superseded; kept as library (`klines` + constants) |

Key reports: `rules_preregistration.md`, `regime_findings.md`,
`walkforward_results.md`, latest `*_backtest_*.txt` per experiment.

## Open items

- Micro-live decision at ~10 base trades (~2 months); gate30-vs-base
  comparison is part of the review.
- Long-side knobs untested: depth-scaled sizing, laddered entries,
  crash-speed/funding conditions, recovery exits, holds >48h, re-entry.
- Pre-registration round 2 when going live; self-gate (strategy's own
  trailing 60d P&L) is the runner-up dial.
- `hl_bot.py` live order path untested; watch the first live entry on the
  HL UI, measure mania-moment slippage.
- Funding costs unmodeled.
