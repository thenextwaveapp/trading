-- db/migrations/20261028_challenge_standings.sql
-- The output of a settled Challenge: one row per entry, its judged place and
-- the headline metrics. Written by runtime/challenge_runner after it runs every
-- entry through the engine over the market window. RLS: readable once the
-- challenge has left draft; written by the service role only. Idempotent.
--   psql "$DATABASE_URL" -f db/migrations/20261028_challenge_standings.sql

CREATE TABLE IF NOT EXISTS public.pf_challenge_standings (
    id            uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    challenge_id  uuid NOT NULL REFERENCES public.pf_challenges(id) ON DELETE CASCADE,
    bot_id        uuid NOT NULL REFERENCES public.pf_bots(id) ON DELETE CASCADE,
    place         integer,                 -- 1 = winner; null = ineligible
    eligible      boolean NOT NULL DEFAULT true,
    score         numeric,                 -- the judge's score (higher = better)
    total_return  numeric,
    max_drawdown  numeric,
    trades        integer,
    created_at    timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (challenge_id, bot_id)
);
CREATE INDEX IF NOT EXISTS pf_challenge_standings_board
    ON public.pf_challenge_standings (challenge_id, place);

ALTER TABLE public.pf_challenge_standings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pf_challenge_standings_read ON public.pf_challenge_standings;
CREATE POLICY pf_challenge_standings_read ON public.pf_challenge_standings FOR SELECT
  USING (EXISTS (SELECT 1 FROM public.pf_challenges c
                 WHERE c.id = challenge_id
                   AND (c.status <> 'draft' OR c.created_by = auth.uid())));
