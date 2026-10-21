# legacy-engine — the config-era paper fleet (pre-weld)

Archived snapshot of the hand-coded, fleet_config.json-driven engine that ran
before the weld (the switch to running pf_bots specs through core/).

- `paper_fleet_config_era.py` — the old engine: signal()/signal_capit()/
  signal_momo(), run_signals/run_churn/run_loser/run_books/run_orders,
  check_exit, cycle(), the VARIANTS/BT/STRATS load from fleet_config.json.
  Superseded by fleet/paper_fleet.py (cycle_db → spec_runtime → core).
- `fleet_dashboard_config_era.py` — the dashboard that read name-keyed state +
  trades CSVs. Superseded by the pf_bots + per-bot-id-state version.
- `fleet_config.json` — the frozen house-fleet definition. The fleet is pf_bots
  now; universes are pf_universes.

Kept for provenance (the validated edges were hand-encoded here first). Nothing
in the live product imports from this folder.
