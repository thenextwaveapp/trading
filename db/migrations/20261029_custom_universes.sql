-- Custom, user-owned universes.
--
-- A universe is a subset of a *market's* instruments. This scopes universes and
-- coins to a market (replacing the hardcoded eqSlugs list in the web) and adds a
-- `saved` flag: an owned custom universe is listed/reusable in the dropdown only
-- when saved, otherwise it's a throwaway tied to a single bot. Both the backtest
-- (core/db.universe_symbols, by slug) and live (spec_runtime, by universe_id)
-- resolve the same pf_universe_coins set, so a custom subset stays backtest==live.
--
-- RLS already allows owner CRUD (pf_universes_rw / pf_universe_coins_rw on
-- owner = auth.uid()) and public reads, so no policy changes are needed. Public
-- read is intentional: anyone viewing a public bot can resolve its universe.

alter table public.pf_universes
  add column if not exists market text not null default 'crypto',
  add column if not exists saved  boolean not null default false;

update public.pf_universes set market = 'equity' where slug in ('mag-7', 'us-equities');
update public.pf_universes set saved = true;  -- everything pre-existing is real/listable

alter table public.pf_coins add column if not exists market text not null default 'crypto';

update public.pf_coins set market = 'equity'
where symbol in (
  select distinct c.coin_symbol
  from pf_universe_coins c
  join pf_universes u on u.id = c.universe_id
  where u.market = 'equity'
);