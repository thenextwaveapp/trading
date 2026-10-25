-- Build flow: per-owner bot names, faster backtest lookup, family defaults.
-- Idempotent. Apply once to an existing project:
--   psql "$DATABASE_URL" -f db/migrations/20261024_build_flow.sql
--
-- The app addresses bots by id now, but names are still the human-facing
-- identity (and the public /bot/:name route), so two bots owned by the same
-- Builder must not share one. The unique index fails loudly if duplicates
-- already exist; resolve those first.

CREATE UNIQUE INDEX IF NOT EXISTS pf_bots_owner_name_key
  ON public.pf_bots (owner, name);

CREATE INDEX IF NOT EXISTS pf_backtests_bot_created_idx
  ON public.pf_backtests (bot_id, created_at DESC);

-- Canonical Setup defaults for the families the engine maps today. Compose
-- carries its own copy so the UI works before this migration is applied; this
-- keeps the API/DB honest for everyone else.
UPDATE public.pf_strategy_families
   SET default_params = '{"runup":0.12,"vol":2.0,"hold":16,"stop":["hh",0.0]}'::jsonb
 WHERE slug = 'pump_short' AND default_params IS NULL;

UPDATE public.pf_strategy_families
   SET default_params = '{"runup":0.12,"vol":2.0,"hold":16,"stop":["hh",0.0],"twosided":true}'::jsonb
 WHERE slug = 'two_sided' AND default_params IS NULL;

UPDATE public.pf_strategy_families
   SET default_params = '{"depth":0.2,"hold":96,"stop":["none",0.0]}'::jsonb
 WHERE slug = 'capit_long' AND default_params IS NULL;

UPDATE public.pf_strategy_families
   SET default_params = '{"runup":0.12,"vol":2.5,"hold":48,"stop":["sig",0.0]}'::jsonb
 WHERE slug = 'momo_long' AND default_params IS NULL;
