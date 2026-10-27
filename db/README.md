# db/

Version-controlled snapshot of the Supabase `public` schema for the paperfleet
app (`pf_*` tables). Until now the schema, RLS, and triggers lived only in the
hosted project — this is what lets a fresh database be stood up from the repo.

## Apply to a fresh database (in order)

```
psql "$DATABASE_URL" -f db/schema.sql      # tables, constraints, enable RLS
psql "$DATABASE_URL" -f db/functions.sql   # signup trigger + event emitters
psql "$DATABASE_URL" -f db/policies.sql     # one RLS policy set per table
```

`policies.sql` is idempotent (drops any existing `pf_*` policy first), so it can
be re-run to reset policies on an existing project.

## Apply incremental changes

Existing projects apply files under `db/migrations/` in filename order:

```
psql "$DATABASE_URL" -f db/migrations/20261024_build_flow.sql
psql "$DATABASE_URL" -f db/migrations/20261024_weather_thresholds.sql
psql "$DATABASE_URL" -f db/migrations/20261025_checks_lexicon.sql
psql "$DATABASE_URL" -f db/migrations/20261026_bot_marks.sql
psql "$DATABASE_URL" -f db/migrations/20261026_bot_trades.sql
psql "$DATABASE_URL" -f db/migrations/20261026_sweeps.sql
```

Migrations are idempotent where possible. `20261024_build_flow.sql` adds the
per-owner bot-name uniqueness the Build flow relies on, an index for the latest
backtest lookup, and canonical `default_params` for the mapped families.
`20261024_weather_thresholds.sql` stores the training-window volatility
terciles with each Weather cell so the live fleet can enforce the gate.
`20261025_checks_lexicon.sql` aligns the `pf_checks` constraints with the
engine's `placebo`/`cost_stress`/`entry_delay` keys and `pass`/`fail` statuses.
`20261026_bot_marks.sql` and `20261026_bot_trades.sql` store the live fleet's
per-cycle marks and trade ledger. `20261026_sweeps.sql` adds the experiment
lab's `pf_sweeps` queue and `pf_sweep_runs` grid results, with RLS following
the parent bot owner.

## Scope

- **Included:** all `pf_*` tables, primary/foreign/unique keys, RLS enable +
  policies, and the trigger functions (`handle_new_user`, `emit_copy_event`,
  `emit_follow_event`) with their triggers.
- **Not included:** seed/reference data (`pf_plans`, `pf_strategy_families`,
  `pf_coins`, and the founder's seeded `fleet-60` universe + bots). A fresh DB
  has the structure but no rows; export data separately when that's needed.
- Other apps share this Supabase project (`dl_*`, `out_*`, …); they are not part
  of paperfleet and are not captured here.

## Regenerate this snapshot

The source of truth is the live DB. These files were generated from
`information_schema` / `pg_catalog` (table DDL), `pg_constraint`
(`pg_get_constraintdef`), `pg_policies`, and `pg_get_functiondef`. Re-pull those
after any schema change and update the files here in the same commit.
