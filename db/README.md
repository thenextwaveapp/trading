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
