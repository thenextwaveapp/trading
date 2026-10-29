-- db/migrations/20261029_seal_read_contract.sql
-- The one BREAKING part of the seal (#3), split out and HELD until the web is
-- ready. It tightens pf_bots_read so a non-owner can read a bot's base row
-- (which carries the Setup: spec/params/condition_filter) ONLY when the bot is
-- fully public and not under seal. `results` and sealed entries then fall to
-- pf_bot_cards + the record tables for everything a non-owner may see — which
-- is exactly how the seal hides the recipe while showing the record.
--
-- DO NOT APPLY until the web reads pf_bot_cards for every other-people's-bot
-- surface (Leaderboard, Builder, BotProfile). Applied alone, `results` bots
-- disappear from those pages, because the app still selects from pf_bots.
--
-- Verified on a Supabase branch 2026-10-28 (see 20261028_challenge_integrity
-- history): with this in place a non-owner sees a sealed/`results` entry's card
-- and record but not its Setup; a public+unsealed bot's Setup stays visible.
--   psql "$DATABASE_URL" -f db/migrations/20261029_seal_read_contract.sql

DROP POLICY IF EXISTS pf_bots_read ON public.pf_bots;
CREATE POLICY pf_bots_read ON public.pf_bots FOR SELECT
  USING (
    owner = auth.uid()
    OR (visibility = 'public'
        AND (sealed_until IS NULL OR sealed_until <= now()))
  );
