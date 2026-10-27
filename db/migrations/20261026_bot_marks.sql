-- db/migrations/20261026_bot_marks.sql
-- Per-bot live marks written by paper_fleet each cycle. One row per bot per cycle.
CREATE TABLE IF NOT EXISTS public.pf_bot_marks (
    id          bigserial PRIMARY KEY,
    bot_id      uuid NOT NULL REFERENCES public.pf_bots(id) ON DELETE CASCADE,
    t           bigint NOT NULL,            -- ms epoch
    equity      numeric NOT NULL,
    ret         numeric,
    open_json   jsonb,
    closed      int,
    win         numeric,
    paused      boolean NOT NULL DEFAULT false,
    kill        boolean NOT NULL DEFAULT false,
    log_tail    text
);
CREATE INDEX IF NOT EXISTS pf_bot_marks_bot_t ON public.pf_bot_marks (bot_id, t DESC);
ALTER TABLE public.pf_bot_marks ENABLE ROW LEVEL SECURITY;
-- read: owner or public bot
CREATE POLICY pf_bot_marks_read ON public.pf_bot_marks FOR SELECT
  USING (EXISTS (SELECT 1 FROM public.pf_bots b WHERE b.id = bot_id
                 AND (b.visibility <> 'private' OR b.owner = auth.uid())));
-- write: service role only (no policy for anon/authenticated writes)