-- db/migrations/20261026_bot_trades.sql
CREATE TABLE IF NOT EXISTS public.pf_bot_trades (
    id          bigserial PRIMARY KEY,
    bot_id      uuid NOT NULL REFERENCES public.pf_bots(id) ON DELETE CASCADE,
    t_sig       bigint NOT NULL,
    exit_t      bigint NOT NULL,
    ticker      text NOT NULL,
    side        text NOT NULL,
    kind        text,
    net         numeric,
    pnl         numeric,
    notional    numeric,
    entry       numeric,
    exit_px     numeric
);
CREATE INDEX IF NOT EXISTS pf_bot_trades_bot_exit ON public.pf_bot_trades (bot_id, exit_t DESC);
ALTER TABLE public.pf_bot_trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY pf_bot_trades_read ON public.pf_bot_trades FOR SELECT
  USING (EXISTS (SELECT 1 FROM public.pf_bots b WHERE b.id = bot_id
                 AND (b.visibility <> 'private' OR b.owner = auth.uid())));

-- db/migrations/20261026_fleet_log.sql
CREATE TABLE IF NOT EXISTS public.pf_fleet_log (
    id      bigserial PRIMARY KEY,
    t       bigint NOT NULL,
    line    text NOT NULL
);
ALTER TABLE public.pf_fleet_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY pf_fleet_log_read ON public.pf_fleet_log FOR SELECT USING (true);