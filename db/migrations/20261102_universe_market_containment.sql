-- Containment: a universe may only contain instruments in its own market.
--
-- This is the DB backstop behind two other layers: the web coin picker (only
-- offers in-market instruments) and the engine's resolve-time filter
-- (core/db._resolve drops off-market coins). It exists so a mislabeled universe
-- can never be *written* — e.g. an fx_spot universe seeded with crypto coins,
-- which produced a bot trading 60 crypto perps under an FX nameplate.
--
-- Fires before insert/update on pf_universe_coins. A null market on either side
-- (legacy rows) is allowed through; only a definite mismatch is rejected.

create or replace function pf_check_universe_coin_market() returns trigger as $$
declare
  u_market text;
  c_market text;
begin
  select market into u_market from pf_universes where id = new.universe_id;
  select market into c_market from pf_coins where symbol = new.coin_symbol;
  if u_market is not null and c_market is not null and u_market <> c_market then
    raise exception
      'instrument % (market %) does not belong to universe % (market %)',
      new.coin_symbol, c_market, new.universe_id, u_market;
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists pf_universe_coin_market on pf_universe_coins;
create trigger pf_universe_coin_market
  before insert or update on pf_universe_coins
  for each row execute function pf_check_universe_coin_market();
