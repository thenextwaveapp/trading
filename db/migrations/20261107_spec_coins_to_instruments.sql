-- StrategySpec JSON: rename the optional `coins` array to `instruments`.
--
-- Background: the assistant / parse-strategy edge functions emitted specs with a
-- bare-ticker `coins` array when a strategy named specific instruments, and the
-- web Builder reads it to seed the custom-instrument picker. The Python engine
-- never read spec.coins (it resolves a bot's universe through
-- pf_universe_instruments), so this is purely a web/LLM contract alignment with
-- the already-renamed instrument tables — no engine or backtest impact.
--
-- The web reads both keys (instruments ?? coins) and the edge functions now emit
-- `instruments`, so this backfill is belt-and-suspenders. It is idempotent: after
-- it runs, no spec still carries a `coins` key.

update public.pf_bots
set spec = (spec - 'coins') || jsonb_build_object('instruments', spec -> 'coins')
where spec ? 'coins';
