-- Rename pf_coins -> pf_instruments and pf_universe_coins -> pf_universe_instruments
-- (coin_symbol -> instrument_symbol). "coin" was the crypto-era name; these
-- tables hold instruments of any market (crypto, equity, fx_spot, …).
--
-- Breaking: ship with the code deploy — the services and web query these names.
-- The snapshot (schema.sql, functions.sql, policies.sql) already reflects the
-- new names.

alter table pf_coins rename to pf_instruments;
alter table pf_instruments rename constraint pf_coins_pkey to pf_instruments_pkey;
alter policy pf_coins_read on pf_instruments rename to pf_instruments_read;

alter table pf_universe_coins rename to pf_universe_instruments;
alter table pf_universe_instruments rename column coin_symbol to instrument_symbol;
alter table pf_universe_instruments
  rename constraint pf_universe_coins_pkey to pf_universe_instruments_pkey;
alter table pf_universe_instruments
  rename constraint pf_universe_coins_universe_id_fkey to pf_universe_instruments_universe_id_fkey;
alter table pf_universe_instruments
  rename constraint pf_universe_coins_coin_symbol_fkey to pf_universe_instruments_instrument_symbol_fkey;
alter policy pf_universe_coins_rw on pf_universe_instruments rename to pf_universe_instruments_rw;
alter policy pf_universe_coins_read on pf_universe_instruments rename to pf_universe_instruments_read;

-- the containment trigger referenced the old table + column — redefine under the
-- new names and retire the old function/trigger.
create or replace function pf_check_universe_instrument_market() returns trigger as $$
declare
  u_market text;
  c_market text;
begin
  select market into u_market from pf_universes where id = new.universe_id;
  select market into c_market from pf_instruments where symbol = new.instrument_symbol;
  if u_market is not null and c_market is not null and u_market <> c_market then
    raise exception
      'instrument % (market %) does not belong to universe % (market %)',
      new.instrument_symbol, c_market, new.universe_id, u_market;
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists pf_universe_coin_market on pf_universe_instruments;
create trigger pf_universe_instrument_market
  before insert or update on pf_universe_instruments
  for each row execute function pf_check_universe_instrument_market();

drop function if exists pf_check_universe_coin_market();
