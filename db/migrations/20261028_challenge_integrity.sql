-- db/migrations/20261028_challenge_integrity.sql
-- The SAFE, additive half of Challenge integrity — applied to prod 2026-10-28.
-- All of this is additive or visibility-neutral, so it ships ahead of the web:
--   * sealed_until column
--   * pf_bot_record_visible() — SECURITY DEFINER, so a record table's policy is
--     not blocked by (and cannot recurse through) the pf_bots row policy
--   * pf_bot_cards — the safe public projection (identity + record, never the
--     Setup) the web reads for a sealed entry
--   * record read policies switched to the helper (same visibility result)
--   * the freeze trigger (#4): once a challenge is past its build window an
--     entry's Setup is frozen, so a legal entry can't be edited to break locks
--
-- The one BREAKING change — tightening pf_bots_read so a sealed/`results` base
-- row hides its Setup from non-owners — is split into
-- 20261029_seal_read_contract.sql and must land WITH the web switch to
-- pf_bot_cards (else `results` bots vanish from the Leaderboard). Idempotent.
--   psql "$DATABASE_URL" -f db/migrations/20261028_challenge_integrity.sql

ALTER TABLE public.pf_bots
    ADD COLUMN IF NOT EXISTS sealed_until timestamp with time zone;

CREATE OR REPLACE FUNCTION public.pf_bot_record_visible(b_id uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.pf_bots b
    WHERE b.id = b_id
      AND (b.visibility <> 'private' OR b.owner = auth.uid())
  );
$$;

-- the safe public projection: identity + record pointers, never the Setup
-- (no spec / params / condition_filter / family_slug / universe_id / direction).
DROP VIEW IF EXISTS public.pf_bot_cards;
CREATE VIEW public.pf_bot_cards
  WITH (security_invoker = off) AS
  SELECT id, owner, fleet_id, name, slug, description, note,
         market, stage, visibility, challenge_id, copied_from,
         version, bt, sealed_until, created_at, updated_at,
         validated_at, launched_at
  FROM public.pf_bots b
  WHERE b.visibility <> 'private' OR b.owner = auth.uid();
GRANT SELECT ON public.pf_bot_cards TO anon, authenticated;

-- record tables read through the definer helper (same result today; stays
-- correct once the base row is sealed by the read-contract migration).
DROP POLICY IF EXISTS pf_backtests_read ON public.pf_backtests;
CREATE POLICY pf_backtests_read ON public.pf_backtests FOR SELECT
  USING (public.pf_bot_record_visible(bot_id));

DROP POLICY IF EXISTS pf_bot_marks_read ON public.pf_bot_marks;
CREATE POLICY pf_bot_marks_read ON public.pf_bot_marks FOR SELECT
  USING (public.pf_bot_record_visible(bot_id));

DROP POLICY IF EXISTS pf_bot_trades_read ON public.pf_bot_trades;
CREATE POLICY pf_bot_trades_read ON public.pf_bot_trades FOR SELECT
  USING (public.pf_bot_record_visible(bot_id));

-- #4: freeze an entry's Setup once its challenge is past the build window. Only
-- the Setup columns are frozen; visibility/stage/bt/record pointers stay
-- writable so the unseal (results -> public) and result write-back still work.
CREATE OR REPLACE FUNCTION public.pf_bots_freeze_entry()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE st text;
BEGIN
  IF NEW.challenge_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT status INTO st FROM public.pf_challenges WHERE id = NEW.challenge_id;
  IF st IN ('sealed', 'live', 'closed') THEN
    IF NEW.spec             IS DISTINCT FROM OLD.spec
    OR NEW.params           IS DISTINCT FROM OLD.params
    OR NEW.condition_filter IS DISTINCT FROM OLD.condition_filter
    OR NEW.family_slug      IS DISTINCT FROM OLD.family_slug
    OR NEW.universe_id      IS DISTINCT FROM OLD.universe_id
    OR NEW.direction        IS DISTINCT FROM OLD.direction THEN
      RAISE EXCEPTION
        'challenge entry %: Setup is frozen once the build window closes', NEW.id
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS pf_bots_freeze_entry ON public.pf_bots;
CREATE TRIGGER pf_bots_freeze_entry BEFORE UPDATE ON public.pf_bots
  FOR EACH ROW EXECUTE FUNCTION public.pf_bots_freeze_entry();
