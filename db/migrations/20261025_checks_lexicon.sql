-- pf_checks speaks the app's vocabulary: the engine emits placebo,
-- cost_stress and entry_delay checks with pass/fail statuses. The live
-- project still carried the pre-lexicon constraints, so every worker insert
-- failed with a check violation. Idempotent.
--
--   psql "$DATABASE_URL" -f db/migrations/20261025_checks_lexicon.sql

ALTER TABLE public.pf_checks DROP CONSTRAINT IF EXISTS pf_checks_key_check;
ALTER TABLE public.pf_checks DROP CONSTRAINT IF EXISTS pf_checks_status_check;
ALTER TABLE public.pf_checks ADD CONSTRAINT pf_checks_status_check
  CHECK (status IN ('pending', 'pass', 'fail'));
