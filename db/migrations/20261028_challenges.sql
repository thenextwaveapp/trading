-- db/migrations/20261028_challenges.sql
-- Challenges: a full bot spec with one hole. A challenge carries the locked
-- `template` spec and a `lock_set` (the open holes + predicates) that the
-- engine (core/challenges.py) enforces on every entry; the market then votes
-- and `judge` ranks the field. A bot carries exactly one challenge_id —
-- entering is a Copy of the template stamped with it. RLS: the author writes;
-- everyone reads a challenge once it is no longer a draft. Idempotent.
--
--   psql "$DATABASE_URL" -f db/migrations/20261028_challenges.sql

CREATE TABLE IF NOT EXISTS public.pf_challenges (
    id            uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    slug          text NOT NULL UNIQUE,
    title         text NOT NULL,
    blurb         text,
    created_by    uuid REFERENCES public.pf_profiles(id) ON DELETE SET NULL,
    market        text NOT NULL DEFAULT 'crypto',
    -- the locked template spec and the lock-set the engine enforces:
    --   lock_set = { "holes": [<spec path>, ...],
    --               "predicates": [{"kind": ..., ...}, ...] }
    template      jsonb NOT NULL,
    lock_set      jsonb NOT NULL DEFAULT '{"holes": [], "predicates": []}'::jsonb,
    judge         text NOT NULL DEFAULT 'return'
        CHECK (judge IN ('return', 'calmar', 'profit_factor', 'low_drawdown',
                         'fewest_trades_positive', 'median_distance')),
    judge_cfg     jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- sealed: entrants' Setups stay hidden (visibility 'results') until close.
    seal          boolean NOT NULL DEFAULT true,
    season        integer,
    week          integer,
    build_open    timestamp with time zone,
    build_close   timestamp with time zone,
    market_open   timestamp with time zone,
    market_close  timestamp with time zone,
    status        text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'open', 'sealed', 'live', 'closed')),
    created_at    timestamp with time zone NOT NULL DEFAULT now(),
    updated_at    timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pf_challenges_status
    ON public.pf_challenges (status, market_close DESC);
CREATE INDEX IF NOT EXISTS pf_challenges_season_week
    ON public.pf_challenges (season, week);

-- A bot belongs to at most one Challenge. Clearing the Challenge keeps the bot.
ALTER TABLE public.pf_bots
    ADD COLUMN IF NOT EXISTS challenge_id uuid
    REFERENCES public.pf_challenges(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS pf_bots_challenge
    ON public.pf_bots (challenge_id) WHERE challenge_id IS NOT NULL;

ALTER TABLE public.pf_challenges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pf_challenges_rw   ON public.pf_challenges;
DROP POLICY IF EXISTS pf_challenges_read ON public.pf_challenges;

-- the author writes their own challenges...
CREATE POLICY pf_challenges_rw ON public.pf_challenges FOR ALL
  USING (created_by = auth.uid())
  WITH CHECK (created_by = auth.uid());

-- ...and anyone reads a challenge once it has left draft (the author always
-- sees their own, draft or not).
CREATE POLICY pf_challenges_read ON public.pf_challenges FOR SELECT
  USING (status <> 'draft' OR created_by = auth.uid());
