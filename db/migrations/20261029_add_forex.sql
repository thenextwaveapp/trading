-- Forex: the seven major USD pairs as an fx_spot universe.
-- binance_symbol holds the Yahoo chart symbol (the engine routes any non-USDT
-- symbol to Yahoo); market='fx_spot' so the OHLC capability rule drops volume
-- indicators and the Builder's universe/coin pickers surface them automatically.
insert into public.pf_coins (symbol, binance_symbol, name, market) values
  ('EURUSD', 'EURUSD=X', 'Euro / US Dollar', 'fx_spot'),
  ('GBPUSD', 'GBPUSD=X', 'British Pound / US Dollar', 'fx_spot'),
  ('USDJPY', 'JPY=X',    'US Dollar / Japanese Yen', 'fx_spot'),
  ('USDCHF', 'CHF=X',    'US Dollar / Swiss Franc', 'fx_spot'),
  ('AUDUSD', 'AUDUSD=X', 'Australian Dollar / US Dollar', 'fx_spot'),
  ('USDCAD', 'CAD=X',    'US Dollar / Canadian Dollar', 'fx_spot'),
  ('NZDUSD', 'NZDUSD=X', 'New Zealand Dollar / US Dollar', 'fx_spot')
on conflict (symbol) do update
  set binance_symbol = excluded.binance_symbol, name = excluded.name, market = excluded.market;

insert into public.pf_universes (slug, name, description, owner, market, saved)
select 'fx-majors', 'FX Majors', 'The seven major USD currency pairs', null, 'fx_spot', true
where not exists (select 1 from public.pf_universes where slug = 'fx-majors');

insert into public.pf_universe_coins (universe_id, coin_symbol)
select u.id, c.sym
from public.pf_universes u
cross join (values ('EURUSD'),('GBPUSD'),('USDJPY'),('USDCHF'),('AUDUSD'),('USDCAD'),('NZDUSD')) as c(sym)
where u.slug = 'fx-majors'
on conflict do nothing;
