-- db/migrations/20261026_sweeps.sql
-- Experiment lab parameter sweeps. The web enqueues a grid; the engine worker
-- expands it, runs one backtest per point, and writes one pf_sweep_runs row
-- per point. RLS follows the parent bot, matching pf_backtests.
CREATE TABLE IF NOT EXISTS public.pf_sweeps (
    id              uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    bot_id          uuid NOT NULL REFERENCES public.pf_bots(id) ON DELETE CASCADE,
    universe_id     uuid REFERENCES public.pf_universes(id) ON DELETE SET NULL,
    universe_slug   text,
    spec            jsonb NOT NULL,
    axes            jsonb NOT NULL,
    window_start    date,
    window_end      date,
    run_count       integer NOT NULL DEFAULT 0,
    completed_count integer NOT NULL DEFAULT 0,
    status          text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'error')),
    error           text,
    created_at      timestamp with time zone NOT NULL DEFAULT now(),
    updated_at      timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pf_sweeps_bot_created
    ON public.pf_sweeps (bot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS pf_sweeps_pending
    ON public.pf_sweeps (created_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS public.pf_sweep_runs (
    id          uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    sweep_id    uuid NOT NULL REFERENCES public.pf_sweeps(id) ON DELETE CASCADE,
    position    integer NOT NULL,
    label       text NOT NULL,
    changes     jsonb NOT NULL DEFAULT '{}'::jsonb,
    stats       jsonb,
    issues      jsonb,
    error       text,
    created_at  timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (sweep_id, position)
);
CREATE INDEX IF NOT EXISTS pf_sweep_runs_sweep_position
    ON public.pf_sweep_runs (sweep_id, position);

ALTER TABLE public.pf_sweeps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_sweep_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pf_sweeps_rw ON public.pf_sweeps;
DROP POLICY IF EXISTS pf_sweep_runs_rw ON public.pf_sweep_runs;

CREATE POLICY pf_sweeps_rw ON public.pf_sweeps FOR ALL
  USING (EXISTS (SELECT 1 FROM public.pf_bots b
                 WHERE b.id = pf_sweeps.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.pf_bots b
                      WHERE b.id = pf_sweeps.bot_id AND b.owner = auth.uid()));

CREATE POLICY pf_sweep_runs_rw ON public.pf_sweep_runs FOR ALL
  USING (EXISTS (SELECT 1 FROM public.pf_sweeps s
                 JOIN public.pf_bots b ON b.id = s.bot_id
                 WHERE s.id = pf_sweep_runs.sweep_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM public.pf_sweeps s
                      JOIN public.pf_bots b ON b.id = s.bot_id
                      WHERE s.id = pf_sweep_runs.sweep_id AND b.owner = auth.uid()));
