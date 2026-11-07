-- Hand-entered trades: the "New trade" ticket on FleetView.
--
-- pf_position_actions is the owner-action queue the live runner drains each
-- cycle (and within seconds via fast_drain). It already carries close /
-- set_stop / set_tp, each a single `value`. Opening a trade needs more than one
-- number — a side, a size, and optional exits — so we add columns for them and
-- extend the action set to include 'open'. All additive and idempotent; the
-- existing columns and RLS (owner may queue actions on their own bot) are
-- untouched.
--
-- A hand-entered trade is owned by a per-user "manual" account bot: a pf_bots
-- row with spec = null (so the trading engine's load_fleet ignores it — it runs
-- no strategy) but stage = 'deployed' and visibility <> 'private' (so the server
-- payload shows it and marks its positions to live price). fast_drain opens and
-- closes its positions directly by bot_id, independent of the strategy cycle.

-- 1. Open-trade parameters on the action queue (nullable; only 'open' sets them).
alter table public.pf_position_actions
  add column if not exists side     smallint,   -- 1 long, -1 short
  add column if not exists notional numeric,    -- dollar size of the position
  add column if not exists stop     numeric,    -- optional stop price
  add column if not exists tp       numeric,    -- optional take-profit price
  add column if not exists symbol   text;       -- binance symbol, e.g. BTCUSDT

-- 2. Allow the 'open' action alongside the existing manage actions. The original
--    constraint was created outside this repo under an unknown name, so drop the
--    likely names defensively before adding the canonical one.
alter table public.pf_position_actions
  drop constraint if exists pf_position_actions_action_check;
alter table public.pf_position_actions
  drop constraint if exists pf_position_actions_action_chk;
alter table public.pf_position_actions
  add constraint pf_position_actions_action_chk
  check (action in ('open', 'close', 'set_stop', 'set_tp'));
